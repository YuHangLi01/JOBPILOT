import { getLLMClient } from '../integrations/llm/client';
import { buildJDParsePrompt } from '../prompts/jd-parse.prompt';
import { JDParsedSchema } from '../types';
import type { JDParsed } from '../types';
import { createLogger } from '../utils/logger';

const log = createLogger('JDParser');

/**
 * JD 结构化解析服务
 * 调用 LLM 将自然语言 JD 转为结构化 JSON
 */
export class JDParserService {
  private llm = getLLMClient();

  async parse(jdText: string): Promise<JDParsed> {
    log.info('开始解析 JD...');

    const prompt = buildJDParsePrompt(jdText);

    const result = await this.llm.chatJSON<JDParsed>(
      [{ role: 'user', content: prompt }],
      (raw) => {
        try {
          const json = JSON.parse(raw);
          // 使用 zod 校验并补全默认值
          const parsed = JDParsedSchema.safeParse(json);
          if (parsed.success) {
            return parsed.data;
          }
          log.warn('JD 解析结果 zod 校验失败', parsed.error.issues);
          // 仍尝试宽松使用
          return JDParsedSchema.parse({
            ...json,
            company_name: json.company_name || '未知公司',
            job_title: json.job_title || '未知岗位',
          });
        } catch {
          return null;
        }
      },
      'JD 解析',
    );

    // 兜底处理
    result.company_name = result.company_name || '未知公司';
    result.job_title = result.job_title || '未知岗位';

    log.info('JD 解析完成', {
      company: result.company_name,
      title: result.job_title,
      skillsCount: result.key_skills.length,
    });

    return result;
  }
}

export const jdParserService = new JDParserService();
