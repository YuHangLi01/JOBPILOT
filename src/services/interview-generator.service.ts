import { getLLMClient } from '../integrations/llm/client';
import { buildInterviewPrompt } from '../prompts/interview.prompt';
import { InterviewQuestionsSchema } from '../types';
import type { LightMemoryPromptContext } from '../prompts/light-memory.prompt';
import type { JDParsed, InterviewQuestion } from '../types';
import { createLogger } from '../utils/logger';

const log = createLogger('InterviewGen');

/**
 * 面试题生成服务
 * 根据 JD 结构化结果生成高概率面试题及回答建议
 */
export class InterviewGeneratorService {
  private llm = getLLMClient();

  async generate(jdParsed: JDParsed, memory?: LightMemoryPromptContext | null): Promise<InterviewQuestion[]> {
    log.info('开始生成面试题...');

    const prompt = buildInterviewPrompt(jdParsed, memory);

    const result = await this.llm.chatJSON<{ questions: InterviewQuestion[] }>(
      [{ role: 'user', content: prompt }],
      (raw) => {
        try {
          const json = JSON.parse(raw);
          // 兼容直接返回数组的情况
          const normalized = Array.isArray(json) ? { questions: json } : json;
          const parsed = InterviewQuestionsSchema.safeParse(normalized);
          if (parsed.success) {
            return parsed.data;
          }
          log.warn('面试题 zod 校验失败', parsed.error.issues);
          // 宽松兼容：只要有 question 字段就尝试使用
          if (normalized.questions && Array.isArray(normalized.questions)) {
            return {
              questions: normalized.questions.map((q: Record<string, unknown>) => ({
                question: String(q.question || ''),
                intent: String(q.intent || ''),
                answer_tips: Array.isArray(q.answer_tips) ? q.answer_tips.map(String) : [],
              })),
            };
          }
          return null;
        } catch {
          return null;
        }
      },
      '面试题生成',
    );

    log.info(`面试题生成完成，共 ${result.questions.length} 题`);
    return result.questions;
  }
}

export const interviewGeneratorService = new InterviewGeneratorService();
