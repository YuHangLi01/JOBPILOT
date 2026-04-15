import type { JDParsed } from '../types';

/**
 * 岗位要求总结 Prompt
 */
export function buildSummaryPrompt(parsed: JDParsed): string {
  return `你是一个资深求职顾问。根据以下岗位结构化信息，生成一段面向求职者的岗位要求总结。

## 岗位信息
- 公司：${parsed.company_name}
- 岗位：${parsed.job_title}
- 地点：${parsed.location || '未注明'}
- 级别：${parsed.seniority || '未注明'}
- 核心技能：${parsed.key_skills.join('、') || '未提取'}
- 职责：${parsed.responsibilities.join('；') || '无'}
- 要求：${parsed.requirements.join('；') || '无'}

## 输出要求
请生成一段中文总结，要求：
1. 100~200 字
2. 包含：这个岗位主要做什么、最重要的 3~5 项能力、适合什么类型的候选人、求职者投递时最该强调什么
3. 语气专业简洁，适合直接发给用户阅读
4. 只输出 JSON 格式：{"summary": "你的总结内容"}
5. 不要输出其他任何内容`;
}
