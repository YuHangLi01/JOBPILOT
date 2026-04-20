import { getLLMClient } from '../integrations/llm/client';
import { buildSummaryPrompt } from '../prompts/summary.prompt';
import { JobSummarySchema } from '../types';
import type { LightMemoryPromptContext } from '../prompts/light-memory.prompt';
import type { JDParsed } from '../types';
import { createLogger } from '../utils/logger';

const log = createLogger('JobSummary');

/**
 * 岗位要求总结服务
 * 将结构化 JD 浓缩为一段求职者易读的总结
 */
export class JobSummaryService {
  private llm = getLLMClient();

  async summarize(jdParsed: JDParsed, memory?: LightMemoryPromptContext | null): Promise<string> {
    log.info('开始生成岗位总结...');

    const prompt = buildSummaryPrompt(jdParsed, memory);

    const result = await this.llm.chatJSON<{ summary: string }>(
      [{ role: 'user', content: prompt }],
      (raw) => {
        try {
          const json = JSON.parse(raw);
          const parsed = JobSummarySchema.safeParse(json);
          if (parsed.success) {
            return parsed.data;
          }
          // 兼容：如果直接返回字符串
          if (typeof json === 'string') {
            return { summary: json };
          }
          // 兼容：尝试其他常见字段名
          if (json.content) return { summary: String(json.content) };
          if (json.text) return { summary: String(json.text) };
          return null;
        } catch {
          // 如果整段内容不是 JSON，当作纯文本总结使用
          if (raw.length > 20 && raw.length < 500) {
            return { summary: raw };
          }
          return null;
        }
      },
      '岗位总结生成',
    );

    log.info('岗位总结生成完成');
    return result.summary;
  }
}

export const jobSummaryService = new JobSummaryService();
