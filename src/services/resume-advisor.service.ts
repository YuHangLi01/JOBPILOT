import { getLLMClient } from '../integrations/llm/client';
import { buildResumeAdvicePrompt } from '../prompts/resume-advice.prompt';
import { ResumeAdviceSchema } from '../types';
import type { LightMemoryPromptContext } from '../prompts/light-memory.prompt';
import type { JDParsed } from '../types';
import { createLogger } from '../utils/logger';

const log = createLogger('ResumeAdvisor');

/**
 * 简历修改建议服务
 * 根据 JD 结构化结果生成针对性的简历优化建议
 */
export class ResumeAdvisorService {
  private llm = getLLMClient();

  async generateAdvice(jdParsed: JDParsed, memory?: LightMemoryPromptContext | null): Promise<string[]> {
    log.info('开始生成简历修改建议...');

    const prompt = buildResumeAdvicePrompt(jdParsed, memory);

    const result = await this.llm.chatJSON<{ suggestions: string[] }>(
      [{ role: 'user', content: prompt }],
      (raw) => {
        try {
          const json = JSON.parse(raw);
          const parsed = ResumeAdviceSchema.safeParse(json);
          if (parsed.success) {
            return parsed.data;
          }
          log.warn('简历建议 zod 校验失败', parsed.error.issues);
          // 尝试兼容：如果返回的是数组本身
          if (Array.isArray(json)) {
            return { suggestions: json.map(String) };
          }
          // 尝试兼容：如果字段名不同
          if (json.advice && Array.isArray(json.advice)) {
            return { suggestions: json.advice.map(String) };
          }
          return null;
        } catch {
          return null;
        }
      },
      '简历建议生成',
    );

    log.info(`简历建议生成完成，共 ${result.suggestions.length} 条`);
    return result.suggestions;
  }
}

export const resumeAdvisorService = new ResumeAdvisorService();
