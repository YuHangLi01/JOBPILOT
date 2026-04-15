import { JD_MIN_LENGTH, JD_MAX_LENGTH } from '../constants';

export interface ValidationResult {
  valid: boolean;
  error?: string;
}

/**
 * 校验用户输入的 JD 文本
 */
export function validateJDInput(text: string | undefined | null): ValidationResult {
  if (!text || typeof text !== 'string') {
    return { valid: false, error: '未收到有效文本，请发送一段职位描述（JD）给我。' };
  }

  const trimmed = text.trim();

  if (trimmed.length < JD_MIN_LENGTH) {
    return {
      valid: false,
      error: `文本太短（最少 ${JD_MIN_LENGTH} 字），请发送完整的职位描述。`,
    };
  }

  if (trimmed.length > JD_MAX_LENGTH) {
    return {
      valid: false,
      error: `文本过长（最多 ${JD_MAX_LENGTH} 字），请精简后再发送。`,
    };
  }

  // 简单判断是否像 JD：至少包含常见职位相关关键词中的某些
  const jdKeywords = [
    '职责', '要求', '岗位', '职位', '负责', '技能', '经验',
    '学历', '薪资', '工作', '任职', '优先', '描述', '招聘',
    'responsibility', 'requirement', 'experience', 'skill',
    'qualification', 'job', 'position', 'role', 'description',
  ];

  const lower = trimmed.toLowerCase();
  const matchCount = jdKeywords.filter((kw) => lower.includes(kw)).length;

  if (matchCount < 2) {
    return {
      valid: false,
      error: '这似乎不是一段职位描述（JD），请发送包含岗位职责、任职要求等内容的文本。',
    };
  }

  return { valid: true };
}

/**
 * 安全解析 JSON，兜底返回 null
 */
export function safeParseJSON<T>(raw: string): T | null {
  try {
    // 有些 LLM 会在 JSON 外面包 markdown code block
    const cleaned = raw
      .replace(/^```(?:json)?\s*/i, '')
      .replace(/\s*```$/i, '')
      .trim();
    return JSON.parse(cleaned) as T;
  } catch {
    return null;
  }
}
