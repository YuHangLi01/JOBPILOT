import type { Request, Response } from 'express';
import { config } from '../config';
import { orchestratorService } from '../services/orchestrator.service';
import { feishuMessageService } from '../integrations/feishu/message';
import { validateJDInput } from '../utils/validator';
import { createLogger } from '../utils/logger';
import { FEISHU_EVENT_TYPE_MESSAGE, EVENT_ID_CACHE_SIZE } from '../constants';
import type { FeishuEventBody, FeishuMessageContent, OrchestratorResult } from '../types';

const log = createLogger('FeishuEventCtrl');

/**
 * 简易事件 ID 去重缓存
 * 飞书会对未及时响应的事件进行重发，需要去重
 */
const processedEvents = new Set<string>();

function markEventProcessed(eventId: string): boolean {
  if (processedEvents.has(eventId)) return false;
  processedEvents.add(eventId);
  // 防止内存泄漏：超过上限时清空
  if (processedEvents.size > EVENT_ID_CACHE_SIZE) {
    processedEvents.clear();
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

    // ===== 4. 先立即响应 200，避免飞书超时重发 =====
    res.json({ code: 0, msg: 'ok' });

    // ===== 5. 异步处理事件 =====
    const eventType = body.header?.event_type;
    if (eventType === FEISHU_EVENT_TYPE_MESSAGE) {
      this.handleMessageEvent(body).catch((err) => {
        log.error('处理消息事件时发生未捕获异常', err instanceof Error ? err.message : err);
      });
    } else {
      log.info(`忽略未处理的事件类型: ${eventType}`);
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

    // ===== 输入校验 =====
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
      const result = await orchestratorService.execute(rawText);
      const replyContent = this.buildResultMessage(result);
      await feishuMessageService.replyText(messageId, replyContent);
      log.info('结果消息回复成功');
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      log.error('主流程执行失败', errMsg);
      await feishuMessageService.replyText(
        messageId,
        `❌ 处理过程中遇到问题：${this.sanitizeErrorMessage(errMsg)}\n\n请稍后重试，或检查 JD 内容是否完整。`,
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
