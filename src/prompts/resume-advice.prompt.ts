import type { JDParsed } from '../types';
import { formatLightMemoryBlock, type LightMemoryPromptContext } from './light-memory.prompt';

/**
 * 简历修改建议 Prompt
 *
 * @param memory 轻量记忆上下文；为 null/undefined 时不附加记忆块
 */
export function buildResumeAdvicePrompt(parsed: JDParsed, memory?: LightMemoryPromptContext | null): string {
  const memoryBlock = formatLightMemoryBlock(memory, 'resume');
  return `你是一位经验丰富的简历优化顾问。根据以下岗位信息，为求职者生成针对性的简历修改建议。

## 岗位信息
- 公司：${parsed.company_name}
- 岗位：${parsed.job_title}
- 级别：${parsed.seniority || '未注明'}
- 核心技能：${parsed.key_skills.join('、') || '未提取'}
- 职责：${parsed.responsibilities.join('；') || '无'}
- 要求：${parsed.requirements.join('；') || '无'}
- 加分项：${parsed.preferred_qualifications.join('；') || '无'}${memoryBlock}
## 输出要求
请给出 5~8 条具体、**可执行**的简历修改建议。每条建议应：
1. 针对该岗位量身定制，不要泛泛而谈；可结合用户画像中的**薄弱项 / 历史缺口**给出差异化建议，但须可落到「改哪段经历、补哪个关键词、怎么写结果」
2. 覆盖以下维度中的至少 4 个：
   - 建议突出哪些项目经验
   - 建议强化哪些技能关键词
   - 建议调整哪些表述方式
   - 哪些经历最适合靠前展示
   - 简历结构/格式建议
3. 每条建议控制在 1~2 句话；使用可执行动词（如「把…改为…」「增加…量化指标」）
4. **不要**与轻量记忆中已出现的建议句逐字或同义重复；须输出**新的**表述

## 输出格式
严格输出 JSON 格式，不要包含任何其他内容：
{"suggestions": ["建议1", "建议2", "建议3", "建议4", "建议5"]}`;
}
