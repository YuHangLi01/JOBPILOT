/**
 * 意图识别：根据消息内容和当前会话状态判断用户意图。
 *
 * 三种意图：
 * - jd_routing: 用户发送了 JD 文本，需要路由到 JD 分析流程
 * - interview_reply: 用户正处于模拟面试中，输入为面试回答
 * - general_chat: 其他通用聊天
 */

export type Intent = 'jd_routing' | 'interview_reply' | 'general_chat';

const JD_KEYWORDS = ['岗位职责', '任职要求', '职位描述', '岗位要求', 'Job Description', 'JD'];
const JD_MIN_LENGTH = 50;

function isJdLike(text: string): boolean {
  const hasKeyword = JD_KEYWORDS.some((kw) => text.includes(kw));
  return hasKeyword && text.length >= JD_MIN_LENGTH;
}

/**
 * 检测用户消息意图。
 *
 * @param text - 已去除 @机器人 标记的纯文本内容
 * @param isInInterview - 当前用户是否正处于面试会话中
 */
export function detectIntent(text: string, isInInterview: boolean): Intent {
  if (isInInterview) return 'interview_reply';
  if (isJdLike(text)) return 'jd_routing';
  return 'general_chat';
}
