import { createHash } from 'crypto';
import { jdParserService } from './jd-parser.service';
import { jobSummaryService } from './job-summary.service';
import { resumeAdvisorService } from './resume-advisor.service';
import { interviewGeneratorService } from './interview-generator.service';
import { memoryService } from './memory.service';
import { feishuBitableService } from '../integrations/feishu/bitable';
import { feishuTaskService } from '../integrations/feishu/task';
import { feishuDocumentService } from '../integrations/feishu/document';
import { DEFAULT_STATUS, DEFAULT_SOURCE } from '../constants';
import { createLogger } from '../utils/logger';
import { buildLightMemoryFromAnalysis } from '../prompts/light-memory.prompt';
import type { MemoryContextForJobAnalysis, OrchestratorResult, BitableRecord, JDParsed, InterviewQuestion } from '../types';
import { ProcessingStatus } from '../types';

const log = createLogger('Orchestrator');

const EMPTY_MEMORY_CONTEXT: MemoryContextForJobAnalysis = {
  profile: null,
  recent_job_records: [],
  summary: null,
  similar_job_records: [],
};

export type OrchestratorExecuteOptions = {
  /** 飞书 open_id 等；不传则不做记忆读写，流程与旧版一致 */
  userId?: string;
};

/**
 * 工作流编排器
 *
 * 职责：
 * 1. 接收原始 JD 文本
 * 2. 按顺序调用各服务完成 LLM 分析
 * 3. 并行调用飞书生态写入（多维表格、任务、文档）
 * 4. 汇总结果并返回
 *
 * 设计原则：
 * - 各飞书写入步骤独立 try/catch，单步失败不阻塞其他步骤
 * - 最终结果始终包含所有步骤的状态（成功或失败原因）
 */
export class OrchestratorService {
  /**
   * 执行完整的 JD 分析与飞书生态写入流程
   */
  async execute(jdText: string, options?: OrchestratorExecuteOptions): Promise<OrchestratorResult> {
    const startTime = Date.now();
    log.info('========== 开始执行 JobPilot 工作流 ==========');

    // ===== 阶段 1：JD 结构化解析（串行，后续步骤依赖解析结果） =====
    log.info('[阶段 1/3] JD 结构化解析...');
    const jdParsed = await jdParserService.parse(jdText);

    // ===== 阶段 1.5：读取轻量记忆（有 userId 且已配置记忆表时生效；失败降级为无记忆） =====
    let memoryCtx: MemoryContextForJobAnalysis = EMPTY_MEMORY_CONTEXT;
    const userId = options?.userId?.trim();
    if (userId) {
      try {
        memoryCtx = await memoryService.getMemoryContextForJobAnalysis(userId, {
          jdSkillTags: jdParsed.key_skills,
        });
      } catch (err) {
        log.warn('记忆读取失败，按无记忆继续', err instanceof Error ? err.message : err);
        memoryCtx = EMPTY_MEMORY_CONTEXT;
      }
    }
    const lightMemory = buildLightMemoryFromAnalysis(memoryCtx);

    // ===== 阶段 2：并行生成总结、简历建议、面试题 =====
    log.info('[阶段 2/3] 并行生成总结、简历建议、面试题...');
    const [jobSummary, resumeSuggestions, interviewQuestions] = await Promise.all([
      jobSummaryService.summarize(jdParsed, lightMemory),
      resumeAdvisorService.generateAdvice(jdParsed, lightMemory),
      interviewGeneratorService.generate(jdParsed, lightMemory),
    ]);

    // ===== 阶段 3：飞书生态写入（并行，各自独立 try/catch） =====
    log.info('[阶段 3/3] 并行写入飞书生态...');

    const [bitableResult, taskResult, documentResult] = await Promise.all([
      this.writeBitable(userId, jdParsed, jobSummary, resumeSuggestions, interviewQuestions),
      this.createTask(jdParsed, jobSummary),
      this.createDocument(jdParsed, jobSummary, resumeSuggestions, interviewQuestions),
      this.persistJobMemory(userId, jdParsed, jobSummary, resumeSuggestions),
    ]);

    const elapsed = Date.now() - startTime;
    log.info(`========== 工作流执行完成，耗时 ${elapsed}ms ==========`, {
      bitable: bitableResult.success ? '✅' : '❌',
      task: taskResult.success ? '✅' : '❌',
      document: documentResult.success ? '✅' : '❌',
    });

    return {
      jdParsed,
      jobSummary,
      resumeSuggestions,
      interviewQuestions,
      bitableResult,
      taskResult,
      documentResult,
    };
  }

  /**
   * 写入多维表格（独立异常处理）
   */
  /** JD 指纹：用于 job_records 去重（不存原文） */
  private jdFingerprint(jdParsed: JDParsed): string {
    const skills = [...jdParsed.key_skills].sort((a, b) => a.localeCompare(b)).join(',');
    const raw = `${jdParsed.company_name}|${jdParsed.job_title}|${skills}`.toLowerCase();
    return createHash('sha256').update(raw).digest('hex').slice(0, 24);
  }

  private buildAnalysisId(userId: string | undefined, jdParsed: JDParsed): string {
    const owner = userId?.trim() || 'anonymous';
    return `${owner}__${this.jdFingerprint(jdParsed)}`;
  }

  /**
   * 写回求职记忆（岗位记录 + rolling 摘要）；失败仅打日志，不影响主流程结果
   */
  private async persistJobMemory(
    userId: string | undefined,
    jdParsed: JDParsed,
    jobSummary: string,
    resumeSuggestions: string[],
  ): Promise<void> {
    if (!userId) return;
    const fp = this.jdFingerprint(jdParsed);
    const summarySnippet = jobSummary.slice(0, 400);
    try {
      await memoryService.refreshAfterJobProcessing({
        userId,
        jdSkillTags: jdParsed.key_skills,
        jobRecord: {
          job_record_id: `${userId}__${fp}`,
          user_id: userId,
          job_date: Date.now(),
          company_name: jdParsed.company_name,
          job_title: jdParsed.job_title,
          location: jdParsed.location,
          skill_tags: jdParsed.key_skills.length > 0 ? jdParsed.key_skills : ['（未从 JD 提取）'],
          gap_skill_tags: [],
          jd_fingerprint: fp,
          processing_status: ProcessingStatus.SUCCESS,
          resume_advice_summary: `岗位总结（截断）：${summarySnippet}\n简历建议：${resumeSuggestions.slice(0, 3).join('；')}`,
          interview_focus_tags: jdParsed.key_skills.slice(0, 8),
        },
      });
    } catch (err) {
      log.warn('求职记忆写回失败（已忽略）', err instanceof Error ? err.message : err);
    }
  }

  private async writeBitable(
    userId: string | undefined,
    jdParsed: JDParsed,
    jobSummary: string,
    resumeSuggestions: string[],
    interviewQuestions: InterviewQuestion[],
  ): Promise<OrchestratorResult['bitableResult']> {
    try {
      const analysisId = this.buildAnalysisId(userId, jdParsed);
      const record: BitableRecord = {
        analysis_id: analysisId,
        company_name: jdParsed.company_name || '未知公司',
        job_title: jdParsed.job_title || '未知岗位',
        location: jdParsed.location || '',
        seniority: jdParsed.seniority || '',
        key_skills: jdParsed.key_skills.join('、'),
        jd_summary: jobSummary,
        resume_suggestions: resumeSuggestions.map((s, i) => `${i + 1}. ${s}`).join('\n'),
        interview_questions: interviewQuestions.map((q) => q.question).join('\n'),
        status: DEFAULT_STATUS,
        created_at: Date.now(),
        source: DEFAULT_SOURCE,
      };

      const { recordId } = await feishuBitableService.upsertMainRecord(record);
      return { success: true, recordId };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.error('多维表格写入失败（已降级）', msg);
      return { success: false, error: msg };
    }
  }

  /**
   * 创建飞书任务（独立异常处理）
   */
  private async createTask(
    jdParsed: JDParsed,
    jobSummary: string,
  ): Promise<OrchestratorResult['taskResult']> {
    try {
      const { taskId } = await feishuTaskService.createFollowUpTask(
        jdParsed.company_name || '未知公司',
        jdParsed.job_title || '未知岗位',
        jobSummary,
      );
      return { success: true, taskId };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.error('飞书任务创建失败（已降级）', msg);
      return { success: false, error: msg };
    }
  }

  /**
   * 创建面试准备文档（独立异常处理）
   */
  private async createDocument(
    jdParsed: JDParsed,
    jobSummary: string,
    resumeSuggestions: string[],
    interviewQuestions: InterviewQuestion[],
  ): Promise<OrchestratorResult['documentResult']> {
    try {
      const { docUrl } = await feishuDocumentService.createInterviewPrepDoc({
        jdParsed,
        jobSummary,
        resumeSuggestions,
        interviewQuestions,
      });
      return { success: true, docUrl };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.error('面试准备文档创建失败（已降级）', msg);
      return { success: false, error: msg };
    }
  }
}

export const legacyOrchestratorService = new OrchestratorService();
