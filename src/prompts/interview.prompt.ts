import type { JDParsed } from '../types';
import { formatLightMemoryBlock, type LightMemoryPromptContext } from './light-memory.prompt';

/**
 * 面试题生成 Prompt
 *
 * @param memory 轻量记忆上下文；为 null/undefined 时不附加记忆块
 */
export function buildInterviewPrompt(parsed: JDParsed, memory?: LightMemoryPromptContext | null): string {
  const memoryBlock = formatLightMemoryBlock(memory, 'interview');
  return `你是一位资深面试官和求职教练。根据以下岗位信息，预测 3 个最可能被问到的面试题，并给出回答建议。

## 岗位信息
- 公司：${parsed.company_name}
- 岗位：${parsed.job_title}
- 级别：${parsed.seniority || '未注明'}
- 核心技能：${parsed.key_skills.join('、') || '未提取'}
- 职责：${parsed.responsibilities.join('；') || '无'}
- 要求：${parsed.requirements.join('；') || '无'}${memoryBlock}
## 输出要求
生成 3 个高概率面试题，每题包含：
1. question：面试题目（表述须**新颖**，勿与常见模板题撞句）
2. intent：出题意图（面试官想考察什么）
3. answer_tips：回答建议要点（3 条），须**可准备、可演练**；若记忆提示用户薄弱项，可用其中 1 条要点引导补强，但不要假设用户未提供的项目细节

若有轻量记忆：至少 1 题可**隐性**对齐用户常见缺口或目标方向，但仍须紧扣本 JD 能力模型。

## 输出格式
严格输出 JSON 格式，不要包含任何其他内容：
{
  "questions": [
    {
      "question": "面试题1",
      "intent": "出题意图1",
      "answer_tips": ["要点1", "要点2", "要点3"]
    },
    {
      "question": "面试题2",
      "intent": "出题意图2",
      "answer_tips": ["要点1", "要点2", "要点3"]
    },
    {
      "question": "面试题3",
      "intent": "出题意图3",
      "answer_tips": ["要点1", "要点2", "要点3"]
    }
  ]
}`;
}
