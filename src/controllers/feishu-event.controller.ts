import type { Request, Response } from 'express';
import { config } from '../config';
import { orchestratorService } from '../services/orchestrator.service';
import { resumeIngestionService } from '../services/resume-ingestion.service';
import { detectIntent } from '../services/intent-detector.service';
import { chatStateService } from '../services/chat-state.service';
import { pythonAgentClient } from '../integrations/python-agent/client';
import { feishuFileService } from '../integrations/feishu/file';
import { feishuMessageService } from '../integrations/feishu/message';
import { buildInterviewInvitationCard } from '../integrations/feishu/card-builder';
import { validateJDInput, validateResumePdf } from '../utils/validator';
import { createLogger } from '../utils/logger';
import {
  FEISHU_EVENT_TYPE_MESSAGE,
  FEISHU_EVENT_TYPE_CARD_ACTION,
  FEISHU_MESSAGE_TYPE_FILE,
  EVENT_ID_CACHE_SIZE,
  EVENT_ID_TTL_MS,
} from '../constants';
import type {
  FeishuCardActionBody,
  FeishuEventBody,
  FeishuFileMessageContent,
  FeishuMessageContent,
  OrchestratorResult,
  ResumeIngestionResult,
} from '../types';

const log = createLogger('FeishuEventCtrl');

/**
 * 简易事件 ID 去重缓存
 * 飞书会对未及时响应的事件进行重发，需要去重
 */
const processedEvents = new Map<string, number>();

function pruneProcessedEvents(now: number): void {
  for (const [eventId, expiresAt] of processedEvents) {
    if (expiresAt <= now) {
      processedEvents.delete(eventId);
    }
  }
  while (processedEvents.size > EVENT_ID_CACHE_SIZE) {
    const oldestKey = processedEvents.keys().next().value;
    if (!oldestKey) break;
    processedEvents.delete(oldestKey);
  }
}

function markEventProcessed(eventId: string): boolean {
  const now = Date.now();
  pruneProcessedEvents(now);
  const expiresAt = processedEvents.get(eventId);
  if (expiresAt && expiresAt > now) return false;
  processedEvents.set(eventId, now + EVENT_ID_TTL_MS);
  if (processedEvents.size > EVENT_ID_CACHE_SIZE) {
    pruneProcessedEvents(now);
  }
  return true;
}

/**
 * 飞书事件处理控制器
 */
export class FeishuEventController {
  /**
   * POST /webhook/feishu - 飞书事件订阅入口
   */
  async handleEvent(req: Request, res: Response): Promise<void> {
    const body = req.body as FeishuEventBody;

    // ===== 1. URL 验证（challenge 握手） =====
    if (body.type === 'url_verification' || body.challenge) {
      log.info('收到飞书 URL 验证请求');
      res.json({ challenge: body.challenge });
      return;
    }

    // ===== 2. 验证 token =====
    const token = body.header?.token || body.token;
    if (token !== config.feishu.verificationToken) {
      log.warn('事件 token 验证失败', { received: token });
      res.status(401).json({ error: 'Invalid verification token' });
      return;
    }

    // ===== 3. 事件去重 =====
    const eventId = body.header?.event_id || '';
    if (eventId && !markEventProcessed(eventId)) {
      log.info(`重复事件，已忽略: ${eventId}`);
      res.json({ code: 0, msg: 'ok (duplicate)' });
      return;
    }

    // ===== 4. 路由事件类型 =====
    const eventType = body.header?.event_type;

    if (eventType === FEISHU_EVENT_TYPE_CARD_ACTION) {
      // 卡片动作：立即返回 toast，然后异步处理
      res.json({ code: 0, toast: { type: 'info', content: '正在启动面试…' } });
      this.handleCardAction(body as unknown as FeishuCardActionBody).catch((err) => {
        log.error('处理卡片动作时发生未捕获异常', err instanceof Error ? err.message : err);
      });
      return;
    }

    // ===== 5. 先立即响应 200，避免飞书超时重发 =====
    res.json({ code: 0, msg: 'ok' });

    // ===== 6. 异步处理消息事件 =====
    if (eventType === FEISHU_EVENT_TYPE_MESSAGE) {
      this.handleMessageEvent(body).catch((err) => {
        log.error('处理消息事件时发生未捕获异常', err instanceof Error ? err.message : err);
      });
    } else {
      log.info(`忽略未处理的事件类型: ${eventType}`);
    }
  }

  /**
   * 处理卡片按钮点击事件（card.action.trigger）
   */
  private async handleCardAction(body: FeishuCardActionBody): Promise<void> {
    const action = body.event?.action?.value?.['action'];
    const company = body.event?.action?.value?.['company'] ?? '';
    const position = body.event?.action?.value?.['position'] ?? '';
    const chatId = body.event?.operator?.open_chat_id ?? body.event?.host?.im_context?.chat_id ?? '';
    const userId = body.event?.operator?.open_id ?? '';

    if (action !== 'start_interview') {
      log.info(`忽略未知卡片动作: ${action}`);
      return;
    }

    if (!chatId) {
      log.warn('卡片动作缺少 chat_id，无法启动面试');
      return;
    }

    log.info(`启动面试会话`, { chatId, company, position });
    chatStateService.startInterview(chatId, chatId);

    try {
      const startResp = await pythonAgentClient.startInterview({
        thread_id: chatId,
        user_id: userId,
        company,
        position,
      });

      const message =
        startResp.next_action?.content ?? '面试开始！请先做一下自我介绍。';
      await feishuMessageService.sendTextToChat(chatId, message);
    } catch (err) {
      log.error('启动面试失败', err instanceof Error ? err.message : err);
      chatStateService.endInterview(chatId);
      await feishuMessageService.sendTextToChat(chatId, '❌ 面试启动失败，请稍后重试。');
    }
  }

  /**
   * 处理消息接收事件
   */
  private async handleMessageEvent(body: FeishuEventBody): Promise<void> {
    const message = body.event?.message;
    const messageId = message?.message_id;
    const chatId = message?.chat_id;
    const messageType = message?.message_type;

    if (!messageId) {
      log.warn('消息事件缺少 message_id');
      return;
    }

    if (messageType === FEISHU_MESSAGE_TYPE_FILE) {
      await this.handleFileMessageEvent(body);
      return;
    }

    // 只处理文本消息
    if (messageType !== 'text') {
      log.info(`忽略非文本消息: type=${messageType}`);
      await feishuMessageService.replyText(
        messageId,
        '🤖 目前我只能处理文本类型的职位描述（JD），请直接发送文字内容给我。',
      );
      return;
    }

    // 提取文本内容
    let rawText = '';
    try {
      const content: FeishuMessageContent = JSON.parse(message?.content || '{}');
      rawText = content.text || '';
    } catch {
      log.warn('消息 content 解析失败');
      rawText = '';
    }

    // 去除 @机器人 的 mention 标签
    rawText = rawText.replace(/@_user_\d+/g, '').trim();

    log.info(`收到用户消息，长度: ${rawText.length}`, {
      messageId,
      chatId,
      senderId: body.event?.sender?.sender_id?.open_id,
    });

    // ===== 意图识别 =====
    const isInInterview = chatId ? chatStateService.isInInterview(chatId) : false;
    const intent = detectIntent(rawText, isInInterview);

    // ===== 面试对话中继 =====
    if (intent === 'interview_reply' && chatId) {
      const state = chatStateService.get(chatId);
      if (state) {
        chatStateService.touch(chatId);
        try {
          const resp = await pythonAgentClient.resumeInterview({
            thread_id: state.sessionId,
            user_input: rawText,
          });
          if (resp.state === 'completed') {
            chatStateService.endInterview(chatId);
            const report = resp.report;
            const summary = report
              ? `面试结束！\n\n${report.transcript_summary}\n\n亮点：${report.highlights.join('；')}\n改进：${report.improvements.join('；')}`
              : '面试结束！感谢参与。';
            await feishuMessageService.replyText(messageId, summary);
          } else {
            const message = resp.next_action?.content ?? '（面试官思考中…）';
            await feishuMessageService.replyText(messageId, message);
          }
        } catch (err) {
          log.error('面试中继失败', err instanceof Error ? err.message : err);
          await feishuMessageService.replyText(messageId, '❌ 面试回复失败，请稍后重试。');
        }
        return;
      }
    }

    // ===== 非 JD 文本：友好提示 =====
    if (intent === 'general_chat') {
      await feishuMessageService.replyText(
        messageId,
        '你好！请发送 JD（招聘职位描述）文本给我，我将为你分析岗位要求、生成简历建议和模拟面试题。',
      );
      return;
    }

    // ===== JD 路由：输入校验 =====
    const validation = validateJDInput(rawText);
    if (!validation.valid) {
      log.info('输入校验未通过', { error: validation.error });
      await feishuMessageService.replyText(messageId, `⚠️ ${validation.error}`);
      return;
    }

    // ===== 发送「处理中」提示 =====
    await feishuMessageService.replyText(
      messageId,
      '⏳ 收到你的 JD，正在为你分析岗位要求、生成简历建议和面试题，请稍候约 20~40 秒...',
    );

    // ===== 执行主流程 =====
    try {
      const openId = body.event?.sender?.sender_id?.open_id?.trim();
      const result = await orchestratorService.execute(rawText, {
        userId: openId ?? '',
        chatId: chatId ?? '',
      });
      const replyContent = this.buildResultMessage(result);
      await feishuMessageService.replyText(messageId, replyContent);
      log.info('结果消息回复成功');

      // ===== 发送面试邀请卡片 =====
      if (result.interviewInvitation?.should_invite) {
        const inv = result.interviewInvitation;
        const card = buildInterviewInvitationCard(inv.suggested_company, inv.suggested_position, inv.cta_text);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        await feishuMessageService.replyInteractiveCard(messageId, card as any);
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      log.error('主流程执行失败', errMsg);
      await feishuMessageService.replyText(
        messageId,
        `❌ 处理过程中遇到问题：${this.sanitizeErrorMessage(errMsg)}\n\n请稍后重试，或检查 JD 内容是否完整。`,
      );
    }
  }

  private async handleFileMessageEvent(body: FeishuEventBody): Promise<void> {
    const message = body.event?.message;
    const messageId = message?.message_id;
    const openId = body.event?.sender?.sender_id?.open_id?.trim();

    if (!messageId) {
      log.warn('文件消息缺少 message_id');
      return;
    }
    if (!openId) {
      await feishuMessageService.replyText(messageId, '⚠️ 未识别到用户身份，暂时无法把简历写入记忆。');
      return;
    }

    let fileContent: FeishuFileMessageContent = {};
    try {
      fileContent = JSON.parse(message?.content || '{}') as FeishuFileMessageContent;
    } catch {
      fileContent = {};
    }

    const fileKey = fileContent.file_key?.trim();
    const contentFilename = fileContent.file_name?.trim() || 'resume.pdf';
    if (!fileKey) {
      await feishuMessageService.replyText(messageId, '⚠️ 未读取到文件标识，无法处理该简历文件。');
      return;
    }

    await feishuMessageService.replyText(messageId, '⏳ 收到你的 PDF 简历，正在解析并写入求职记忆，请稍候...');

    try {
      const downloaded = await feishuFileService.downloadMessageFile(messageId, fileKey);
      const filename =
        downloaded.filename && !downloaded.filename.endsWith('.bin') ? downloaded.filename : contentFilename;
      const validation = validateResumePdf({
        filename,
        mimetype: downloaded.mimeType,
        size: downloaded.buffer.length,
        buffer: downloaded.buffer,
      });
      if (!validation.valid) {
        await feishuMessageService.replyText(messageId, `⚠️ ${validation.error}`);
        return;
      }

      const result = await resumeIngestionService.ingest({
        userId: openId,
        filename,
        buffer: downloaded.buffer,
        source: 'feishu_file_message',
      });
      await feishuMessageService.replyText(messageId, this.buildResumeImportMessage(result));
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.error('处理 PDF 简历失败', msg);
      await feishuMessageService.replyText(
        messageId,
        `❌ 简历导入失败：${this.sanitizeErrorMessage(msg)}\n\n请确认上传的是可读取的 PDF 简历后重试。`,
      );
    }
  }

  /**
   * 构建最终回复消息
   */
  private buildResultMessage(result: OrchestratorResult): string {
    const { jdParsed, jobSummary, resumeSuggestions, interviewQuestions, bitableResult, taskResult, documentResult } =
      result;

    const lines: string[] = [];

    // 标题
    lines.push(`✅ 岗位分析完成`);
    lines.push(`━━━━━━━━━━━━━━━━━━`);
    lines.push(``);

    // 基本信息
    lines.push(`🏢 ${jdParsed.company_name} · ${jdParsed.job_title}`);
    if (jdParsed.location) lines.push(`📍 ${jdParsed.location}`);
    if (jdParsed.seniority) lines.push(`📊 ${jdParsed.seniority}`);
    if (jdParsed.key_skills.length > 0) {
      lines.push(`🔑 核心技能：${jdParsed.key_skills.slice(0, 6).join('、')}`);
    }
    lines.push(``);

    // 岗位总结
    lines.push(`📋 【岗位要求总结】`);
    lines.push(jobSummary);
    lines.push(``);

    // 简历建议（取前 5 条）
    lines.push(`✏️ 【简历修改建议】`);
    const topSuggestions = resumeSuggestions.slice(0, 5);
    topSuggestions.forEach((s, i) => {
      lines.push(`${i + 1}. ${s}`);
    });
    lines.push(``);

    // 面试题
    lines.push(`🎯 【可能面试题】`);
    interviewQuestions.forEach((q, i) => {
      lines.push(`Q${i + 1}: ${q.question}`);
      lines.push(`  💡 意图：${q.intent}`);
      lines.push(`  📝 要点：${q.answer_tips.join('；')}`);
      lines.push(``);
    });

    // 执行状态
    lines.push(`━━━━━━━━━━━━━━━━━━`);
    lines.push(`📊 执行状态：`);
    lines.push(`  ${bitableResult.success ? '✅' : '❌'} 多维表格${bitableResult.success ? '已写入' : '写入失败'}`);
    lines.push(`  ${taskResult.success ? '✅' : '❌'} 跟进任务${taskResult.success ? '已创建' : '创建失败'}`);
    lines.push(
      `  ${documentResult.success ? '✅' : '❌'} 面试准备文档${documentResult.success ? '已生成' : '生成失败'}`,
    );

    // 文档链接
    if (documentResult.success && documentResult.docUrl) {
      lines.push(``);
      lines.push(`📄 面试准备文档：${documentResult.docUrl}`);
    }

    lines.push(``);
    lines.push(`💪 祝你求职顺利！有新的 JD 随时发给我。`);

    return lines.join('\n');
  }

  private buildResumeImportMessage(result: ResumeIngestionResult): string {
    const lines: string[] = [];
    const patch = result.profilePatch;

    lines.push('✅ 简历已导入求职记忆');
    lines.push('━━━━━━━━━━━━━━━━━━');
    lines.push(`📄 文件：${result.filename}`);
    if (patch.target_roles?.length) lines.push(`🎯 目标岗位：${patch.target_roles.join('、')}`);
    if (patch.preferred_cities?.length) lines.push(`📍 期望城市：${patch.preferred_cities.join('、')}`);
    if (patch.core_skill_tags?.length) lines.push(`🔑 核心技能：${patch.core_skill_tags.slice(0, 8).join('、')}`);
    if (patch.resume_focus_summary) {
      lines.push('');
      lines.push('🧠 记忆摘要：');
      lines.push(patch.resume_focus_summary);
    }
    lines.push('');
    lines.push('后续你再发送 JD 时，我会结合这份简历记忆给出更贴合的总结、简历建议和面试题。');

    return lines.join('\n');
  }

  /**
   * 脱敏错误信息，不暴露敏感细节
   */
  private sanitizeErrorMessage(msg: string): string {
    // 移除可能包含的 API key、token 等
    const sanitized = msg
      .replace(/Bearer\s+\S+/gi, 'Bearer [REDACTED]')
      .replace(/sk-\S+/g, '[REDACTED]')
      .replace(/cli_\S+/g, '[REDACTED]');

    // 截断过长的错误信息
    if (sanitized.length > 100) {
      return sanitized.substring(0, 100) + '...';
    }
    return sanitized;
  }
}

export const feishuEventController = new FeishuEventController();
