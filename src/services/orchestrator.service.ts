import { v4 as uuidv4 } from 'uuid';
import { config } from '../config';
import { createLogger } from '../utils/logger';
import { pythonAgentClient } from '../integrations/python-agent/client';
import { PythonAgentError } from '../integrations/python-agent/errors';
import { legacyOrchestratorService } from './orchestrator.legacy';
import type { OrchestratorResult } from '../types';
import type { JdRoutingResponse } from '../integrations/python-agent/types';

export type { OrchestratorExecuteOptions } from './orchestrator.legacy';

const log = createLogger('Orchestrator');

/**
 * 将 Python Agent 的响应映射为 Node.js 侧的 OrchestratorResult。
 *
 * 说明：Python Agent 负责 AI 分析（classification/results），
 * 飞书副作用（bitable/task/document）由 Node.js Gateway 层独立处理，
 * 因此 bitableResult / taskResult / documentResult 在此填入空占位值。
 */
function mapPythonResponseToOrchestratorResult(res: JdRoutingResponse): OrchestratorResult {
  const { classification, results } = res;
  const rawInvitation = results.interview_invitation ?? undefined;

  return {
    jdParsed: {
      company_name: '',
      job_title: classification.sub_type,
      location: '',
      job_type: classification.job_type,
      responsibilities: [],
      requirements: [],
      preferred_qualifications: [],
      key_skills: [],
      seniority: classification.level,
      summary: results.jd_summary,
    },
    jobSummary: results.jd_summary,
    resumeSuggestions: (results.resume_advice ?? []).map((item) => item.advice),
    interviewQuestions: (results.interview_questions ?? []).map((q) => ({
      question: q.question,
      intent: q.intent,
      answer_tips: q.answer_points,
    })),
    // 飞书副作用由 Gateway 层处理，Python Agent 不直接执行写操作
    bitableResult: { success: false },
    taskResult: { success: false },
    documentResult: { success: false },
    interviewInvitation: rawInvitation?.should_invite
      ? {
          should_invite: rawInvitation.should_invite,
          reason: rawInvitation.reason,
          suggested_company: rawInvitation.suggested_company,
          suggested_position: rawInvitation.suggested_position,
          cta_text: rawInvitation.cta_text,
          session_seed: rawInvitation.session_seed,
        }
      : undefined,
  };
}

/**
 * 工作流编排器（双栈路由版）
 *
 * - USE_PYTHON_AGENT=true：调用 Python Agent HTTP 接口，失败时自动 fallback 到 legacy
 * - USE_PYTHON_AGENT=false（默认）：直接调用 legacy 实现，行为与改造前完全一致
 *
 * 对外导出签名与改造前相同，调用方（controllers）零改动。
 */
export class OrchestratorService {
  async execute(
    jdText: string,
    options?: { userId?: string; chatId?: string },
  ): Promise<OrchestratorResult> {
    const requestId = uuidv4();

    if (config.pythonAgent.usePythonAgent) {
      try {
        log.info('[Orchestrator] 使用 Python Agent 执行工作流', { request_id: requestId });

        const res = await pythonAgentClient.postJdRouting({
          jd_text: jdText,
          user_id: options?.userId ?? '',
          request_id: requestId,
          user_context: {
            preferred_lang: 'zh',
            feishu_chat_id: options?.chatId ?? null,
          },
        });

        log.info('[Orchestrator] Python Agent 执行成功', { request_id: requestId });
        return mapPythonResponseToOrchestratorResult(res);
      } catch (err) {
        if (err instanceof PythonAgentError) {
          log.warn('Python Agent unreachable, falling back to legacy', {
            request_id: requestId,
            code: err.code,
            retryable: err.retryable,
            message: err.message,
          });
        } else {
          log.warn('Python Agent 调用发生未预期错误，降级到 legacy', {
            request_id: requestId,
            error: err instanceof Error ? err.message : String(err),
          });
        }
        return legacyOrchestratorService.execute(jdText, options);
      }
    }

    return legacyOrchestratorService.execute(jdText, options);
  }
}

export const orchestratorService = new OrchestratorService();
