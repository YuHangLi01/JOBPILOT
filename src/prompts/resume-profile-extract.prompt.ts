export function buildResumeProfileExtractPrompt(resumeText: string): string {
  return `你是一位求职顾问，请从下面的简历文本中提取可写入候选人求职记忆画像的信息。

## 输出目标
请严格输出 JSON，不要附加解释、markdown 或多余文本。

JSON 结构如下：
{
  "target_roles": ["候选人明确投递或适合的岗位，最多 5 个"],
  "target_industries": ["候选人经历集中行业，最多 5 个"],
  "preferred_cities": ["候选人简历中明确提到的期望城市，最多 5 个"],
  "years_of_experience": 3,
  "core_skill_tags": ["核心技能标签，最多 12 个"],
  "weak_skill_tags": ["简历中明显欠缺、但从经历可推断仍需补强的技能，最多 8 个"],
  "certifications": "证书、资质、语言成绩等，若没有则省略或空字符串",
  "resume_focus_summary": "80~180 字，概括候选人的最值得强调经历、技能和亮点",
  "constraints_summary": "80~160 字，概括求职约束，如城市、工作方式、行业偏好、学历或经验边界；如果无法判断则输出空字符串"
}

## 提取规则
1. 只根据简历原文提取，不要虚构不存在的信息。
2. target_roles 优先提取候选人现有/最近岗位、项目方向和求职意图。
3. preferred_cities 只有在简历明确出现期望城市、所在城市或求职地偏好时才填写。
4. years_of_experience 输出整数，按简历最合理的工作年限估算；无法判断则省略该字段。
5. weak_skill_tags 只能写从简历内容可推断出的潜在短板，避免泛泛而谈。
6. 数组请去重，保留中文或英文原词均可，但要简洁。
7. 信息缺失时：数组输出空数组，字符串输出空字符串，可选数字字段省略。

## 简历文本
${resumeText}`;
}
