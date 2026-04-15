import type { JDParsed } from '../types';

/**
 * 简历修改建议 Prompt
 */
export function buildResumeAdvicePrompt(parsed: JDParsed): string {
  return `你是一位经验丰富的简历优化顾问。根据以下岗位信息，为求职者生成针对性的简历修改建议。

## 岗位信息
- 公司：${parsed.company_name}
- 岗位：${parsed.job_title}
- 级别：${parsed.seniority || '未注明'}
- 核心技能：${parsed.key_skills.join('、') || '未提取'}
- 职责：${parsed.responsibilities.join('；') || '无'}
- 要求：${parsed.requirements.join('；') || '无'}
- 加分项：${parsed.preferred_qualifications.join('；') || '无'}

## 输出要求
请给出 5~8 条具体、可操作的简历修改建议。每条建议应：
1. 针对该岗位量身定制，不要泛泛而谈
2. 覆盖以下维度中的至少 4 个：
   - 建议突出哪些项目经验
   - 建议强化哪些技能关键词
   - 建议调整哪些表述方式
   - 哪些经历最适合靠前展示
   - 简历结构/格式建议
3. 每条建议控制在 1~2 句话

## 输出格式
严格输出 JSON 格式，不要包含任何其他内容：
{"suggestions": ["建议1", "建议2", "建议3", "建议4", "建议5"]}`;
}
