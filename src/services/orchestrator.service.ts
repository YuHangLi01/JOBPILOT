import { jdParserService } from './jd-parser.service';
import { jobSummaryService } from './job-summary.service';
import { resumeAdvisorService } from './resume-advisor.service';
import { interviewGeneratorService } from './interview-generator.service';
import { feishuBitableService } from '../integrations/feishu/bitable';
import { feishuTaskService } from '../integrations/feishu/task';
import { feishuDocumentService } from '../integrations/feishu/document';
import { DEFAULT_STATUS, DEFAULT_SOURCE } from '../constants';
import { createLogger } from '../utils/logger';
import type { OrchestratorResult, BitableRecord, JDParsed, InterviewQuestion } from '../types';

const log = createLogger('Orchestrator');

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
  async execute(jdText: string): Promise<OrchestratorResult> {
    const startTime = Date.now();
    log.info('========== 开始执行 JobPilot 工作流 ==========');

    // ===== 阶段 1：JD 结构化解析（串行，后续步骤依赖解析结果） =====
    log.info('[阶段 1/3] JD 结构化解析...');
    const jdParsed = await jdParserService.parse(jdText);

    // ===== 阶段 2：并行生成总结、简历建议、面试题 =====
    log.info('[阶段 2/3] 并行生成总结、简历建议、面试题...');
    const [jobSummary, resumeSuggestions, interviewQuestions] = await Promise.all([
      jobSummaryService.summarize(jdParsed),
      resumeAdvisorService.generateAdvice(jdParsed),
      interviewGeneratorService.generate(jdParsed),
    ]);

    // ===== 阶段 3：飞书生态写入（并行，各自独立 try/catch） =====
    log.info('[阶段 3/3] 并行写入飞书生态...');

    const [bitableResult, taskResult, documentResult] = await Promise.all([
      this.writeBitable(jdParsed, jobSummary, resumeSuggestions, interviewQuestions),
      this.createTask(jdParsed, jobSummary),
      this.createDocument(jdParsed, jobSummary, resumeSuggestions, interviewQuestions),
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
  private async writeBitable(
    jdParsed: JDParsed,
    jobSummary: string,
    resumeSuggestions: string[],
    interviewQuestions: InterviewQuestion[],
  ): Promise<OrchestratorResult['bitableResult']> {
    try {
      const record: BitableRecord = {
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

      const { recordId } = await feishuBitableService.addRecord(record);
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

export const orchestratorService = new OrchestratorService();
