import type { BitableFieldSchemaSpec } from '../types';

// ============================================
// 业务常量
// ============================================

/** JD 文本最小有效长度 */
export const JD_MIN_LENGTH = 50;

/** JD 文本最大长度（防滥用） */
export const JD_MAX_LENGTH = 10000;

/** 默认投递状态 */
export const DEFAULT_STATUS = '待投递';

/** 默认来源 */
export const DEFAULT_SOURCE = '飞书聊天输入';

/** 任务默认截止天数 */
export const TASK_DUE_DAYS = 2;

/** 飞书 API 基地址 */
export const FEISHU_API_BASE = 'https://open.feishu.cn/open-apis';

/** 已处理事件 ID 缓存大小（简易去重） */
export const EVENT_ID_CACHE_SIZE = 500;

/** 已处理事件缓存 TTL，避免飞书重试导致重复执行 */
export const EVENT_ID_TTL_MS = 10 * 60 * 1000;

/** 飞书消息事件类型 */
export const FEISHU_EVENT_TYPE_MESSAGE = 'im.message.receive_v1';

/** 飞书文件消息类型 */
export const FEISHU_MESSAGE_TYPE_FILE = 'file';

/** 简历 PDF 最大大小 */
export const RESUME_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

/** 多维表格字段映射（字段名 → 表头显示名） */
export const BITABLE_FIELD_MAP: Record<string, string> = {
  analysis_id: '分析ID',
  company_name: '公司名称',
  job_title: '岗位名称',
  location: '工作地点',
  seniority: '级别要求',
  key_skills: '核心技能',
  jd_summary: '岗位总结',
  resume_suggestions: '简历建议',
  interview_questions: '面试题',
  status: '投递状态',
  created_at: '创建时间',
  source: '来源',
};

/** 求职记忆：user_profile 表（字段 key → 飞书列名） */
export const MEMORY_USER_PROFILE_FIELD_MAP: Record<string, string> = {
  user_id: '用户ID',
  profile_version: '画像版本',
  target_roles: '目标岗位',
  target_industries: '目标行业',
  preferred_cities: '期望城市',
  work_mode: '工作模式',
  years_of_experience: '工作年限',
  seniority_preference: '职级偏好',
  core_skill_tags: '核心技能',
  weak_skill_tags: '薄弱技能',
  certifications: '证书资质',
  resume_focus_summary: '简历重点摘要',
  constraints_summary: '约束条件摘要',
  last_active_at: '最近活跃时间',
  updated_at: '更新时间',
};

/** 求职记忆：job_records 表 */
export const MEMORY_JOB_RECORDS_FIELD_MAP: Record<string, string> = {
  job_record_id: '记录ID',
  user_id: '用户ID',
  job_date: '处理时间',
  company_name: '公司名称',
  job_title: '岗位名称',
  location: '工作地点',
  job_type: '工作类型',
  seniority: '级别要求',
  skill_tags: '技能标签',
  matched_skill_tags: '匹配技能',
  gap_skill_tags: '技能缺口',
  fit_score: '匹配度',
  decision: '决策建议',
  decision_reason_summary: '决策原因',
  resume_advice_summary: '简历建议摘要',
  interview_focus_tags: '面试重点',
  similarity_bucket: '相似度档位',
  similar_job_refs_json: '相似岗位引用',
  jd_fingerprint: 'JD指纹',
  processing_status: '处理状态',
  error_code: '错误码',
  error_message: '错误信息',
  created_at: '创建时间',
  updated_at: '更新时间',
};

/** 求职记忆：memory_summary 表 */
export const MEMORY_SUMMARY_FIELD_MAP: Record<string, string> = {
  summary_id: '汇总ID',
  user_id: '用户ID',
  period_key: '统计周期',
  computed_at: '计算时间',
  source_record_count: '来源记录数',
  top_target_role_tags: '高频目标岗位',
  top_skill_gap_tags: '高频技能缺口',
  top_strength_tags: '优势标签',
  weak_points_summary: '薄弱项摘要',
  recent_similar_job_advice: '相似岗位建议',
  action_plan_summary: '行动计划',
  evidence_job_ids_json: '证据记录',
  summary_version: '总结版本',
  updated_at: '更新时间',
};

/** 相似岗位检索：最近条数上限（技能标签重叠粗排） */
export const MEMORY_RECENT_JOB_RECORDS_LIMIT = 20;

/** 注入 LLM / prompt 的最近岗位条数 */
export const MEMORY_CONTEXT_SIMILAR_JOBS_N = 5;

/** 飞书多维表格字段 type（常用子集） */
const FEISHU_FIELD = { TEXT: 1, NUMBER: 2, DATE: 5 } as const;

function buildBitableFieldSchema(
  fieldMap: Record<string, string>,
  overrides: Partial<Record<string, number>>,
): BitableFieldSchemaSpec {
  const fieldTypes: Record<string, number> = {};
  for (const key of Object.keys(fieldMap)) {
    fieldTypes[key] = overrides[key] ?? FEISHU_FIELD.TEXT;
  }
  return { fieldMap, fieldTypes };
}

/** 主业务求职台账表：与 BITABLE_FIELD_MAP 一致，写入前自动补列 */
export const BITABLE_MAIN_SCHEMA = buildBitableFieldSchema(BITABLE_FIELD_MAP, {
  created_at: FEISHU_FIELD.DATE,
});

/** 记忆表 user_profile：缺列时按此建列（默认文本，避免单选/多选选项依赖） */
export const MEMORY_USER_PROFILE_SCHEMA = buildBitableFieldSchema(MEMORY_USER_PROFILE_FIELD_MAP, {
  profile_version: FEISHU_FIELD.NUMBER,
  years_of_experience: FEISHU_FIELD.NUMBER,
  last_active_at: FEISHU_FIELD.DATE,
  updated_at: FEISHU_FIELD.DATE,
});

/** 记忆表 job_records */
export const MEMORY_JOB_RECORDS_SCHEMA = buildBitableFieldSchema(MEMORY_JOB_RECORDS_FIELD_MAP, {
  job_date: FEISHU_FIELD.DATE,
  created_at: FEISHU_FIELD.DATE,
  updated_at: FEISHU_FIELD.DATE,
  fit_score: FEISHU_FIELD.NUMBER,
});

/** 记忆表 memory_summary */
export const MEMORY_SUMMARY_SCHEMA = buildBitableFieldSchema(MEMORY_SUMMARY_FIELD_MAP, {
  computed_at: FEISHU_FIELD.DATE,
  updated_at: FEISHU_FIELD.DATE,
  source_record_count: FEISHU_FIELD.NUMBER,
  summary_version: FEISHU_FIELD.NUMBER,
});
