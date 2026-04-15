/**
 * JD 结构化解析 Prompt
 */
export function buildJDParsePrompt(jdText: string): string {
  return `你是一个专业的招聘信息分析助手。请仔细阅读下面的职位描述（JD），然后提取结构化信息。

## 输出要求
请严格输出 JSON 格式，不要包含任何额外的文字、解释或 markdown 标记。
JSON 结构如下：

{
  "company_name": "公司名称，若未提及则填 '未知公司'",
  "job_title": "岗位名称，若未提及则填 '未知岗位'",
  "location": "工作地点，若未提及则填空字符串",
  "job_type": "工作类型（全职/兼职/实习/远程等），若未提及则填空字符串",
  "responsibilities": ["岗位职责列表，每条为一个字符串"],
  "requirements": ["任职要求列表，每条为一个字符串"],
  "preferred_qualifications": ["优先条件/加分项列表，若没有则为空数组"],
  "key_skills": ["核心技能关键词列表，提取 5-10 个"],
  "seniority": "级别要求（初级/中级/高级/资深等），若未提及则填空字符串",
  "summary": "用一两句话概括这个岗位的核心定位"
}

## 注意事项
1. 若原文中某个字段的信息不存在，字符串字段填空字符串 ""，数组字段填空数组 []。
2. key_skills 应尽量从职责和要求中提取具体技术或能力关键词，而非笼统描述。
3. 只输出 JSON，不要输出其他任何内容。

## 职位描述原文
${jdText}`;
}
