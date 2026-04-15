import type { JDParsed } from '../types';

/**
 * 面试题生成 Prompt
 */
export function buildInterviewPrompt(parsed: JDParsed): string {
  return `你是一位资深面试官和求职教练。根据以下岗位信息，预测 3 个最可能被问到的面试题，并给出回答建议。

## 岗位信息
- 公司：${parsed.company_name}
- 岗位：${parsed.job_title}
- 级别：${parsed.seniority || '未注明'}
- 核心技能：${parsed.key_skills.join('、') || '未提取'}
- 职责：${parsed.responsibilities.join('；') || '无'}
- 要求：${parsed.requirements.join('；') || '无'}

## 输出要求
生成 3 个高概率面试题，每题包含：
1. question：面试题目
2. intent：出题意图（面试官想考察什么）
3. answer_tips：回答建议要点（3 条）

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
