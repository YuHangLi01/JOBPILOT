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
 * 将 Python Agent 的 snake_case 响应映射为 OrchestratorResult（camelCase）。
 */
function mapPythonResponseToOrchestratorResult(res: JdRoutingResponse): OrchestratorResult {
  return {
    jdParsed: res.jd_parsed,
    jobSummary: res.job_summary,
    resumeSuggestions: res.resume_suggestions,
    interviewQuestions: res.interview_questions,
    bitableResult: {
      success: res.bitable_result.success,
      recordId: res.bitable_result.record_id,
      error: res.bitable_result.error,
    },
    taskResult: {
      success: res.task_result.success,
      taskId: res.task_result.task_id,
      error: res.task_result.error,
    },
    documentResult: {
      success: res.document_result.success,
      docUrl: res.document_result.doc_url,
      error: res.document_result.error,
    },
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
    options?: { userId?: string },
  ): Promise<OrchestratorResult> {
    const requestId = uuidv4();

    if (config.pythonAgent.usePythonAgent) {
      try {
        log.info('[Orchestrator] 使用 Python Agent 执行工作流', { request_id: requestId });

        const res = await pythonAgentClient.postJdRouting({
          jd_text: jdText,
          user_id: options?.userId,
          request_id: requestId,
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
