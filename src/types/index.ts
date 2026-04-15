import { z } from 'zod';

// ============================================
// JD 解析结果 Schema
// ============================================
export const JDParsedSchema = z.object({
  company_name: z.string().default('未知公司'),
  job_title: z.string().default('未知岗位'),
  location: z.string().default(''),
  job_type: z.string().default(''),
  responsibilities: z.array(z.string()).default([]),
  requirements: z.array(z.string()).default([]),
  preferred_qualifications: z.array(z.string()).default([]),
  key_skills: z.array(z.string()).default([]),
  seniority: z.string().default(''),
  summary: z.string().default(''),
});
export type JDParsed = z.infer<typeof JDParsedSchema>;

// ============================================
// 岗位总结 Schema
// ============================================
export const JobSummarySchema = z.object({
  summary: z.string(),
});
export type JobSummary = z.infer<typeof JobSummarySchema>;

// ============================================
// 简历建议 Schema
// ============================================
export const ResumeAdviceSchema = z.object({
  suggestions: z.array(z.string()).min(1),
});
export type ResumeAdvice = z.infer<typeof ResumeAdviceSchema>;

// ============================================
// 面试题 Schema
// ============================================
export const InterviewQuestionSchema = z.object({
  question: z.string(),
  intent: z.string(),
  answer_tips: z.array(z.string()).min(1),
});
export const InterviewQuestionsSchema = z.object({
  questions: z.array(InterviewQuestionSchema).min(1),
});
export type InterviewQuestion = z.infer<typeof InterviewQuestionSchema>;
export type InterviewQuestions = z.infer<typeof InterviewQuestionsSchema>;

// ============================================
// 飞书事件类型
// ============================================
export interface FeishuEventBody {
  schema?: string;
  header?: {
    event_id: string;
    event_type: string;
    create_time: string;
    token: string;
    app_id: string;
    tenant_key: string;
  };
  event?: {
    sender?: {
      sender_id?: {
        open_id?: string;
        user_id?: string;
        union_id?: string;
      };
      sender_type?: string;
    };
    message?: {
      message_id?: string;
      root_id?: string;
      parent_id?: string;
      create_time?: string;
      chat_id?: string;
      chat_type?: string;
      message_type?: string;
      content?: string;
    };
  };
  // v1 challenge 验证
  challenge?: string;
  token?: string;
  type?: string;
}

export interface FeishuMessageContent {
  text: string;
}

// ============================================
// 多维表格记录
// ============================================
export interface BitableRecord {
  company_name: string;
  job_title: string;
  location: string;
  seniority: string;
  key_skills: string;
  jd_summary: string;
  resume_suggestions: string;
  interview_questions: string;
  status: string;
  created_at: number;
  source: string;
}

// ============================================
// 编排结果
// ============================================
export interface OrchestratorResult {
  jdParsed: JDParsed;
  jobSummary: string;
  resumeSuggestions: string[];
  interviewQuestions: InterviewQuestion[];
  bitableResult: {
    success: boolean;
    recordId?: string;
    error?: string;
  };
  taskResult: {
    success: boolean;
    taskId?: string;
    error?: string;
  };
  documentResult: {
    success: boolean;
    docUrl?: string;
    error?: string;
  };
}

// ============================================
// LLM 调用相关
// ============================================
export interface LLMMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LLMResponse {
  content: string;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

// ============================================
// 飞书 API 响应
// ============================================
export interface FeishuTokenResponse {
  code: number;
  msg: string;
  tenant_access_token?: string;
  expire?: number;
}

export interface FeishuBitableResponse {
  code: number;
  msg: string;
  data?: {
    record?: {
      record_id: string;
    };
  };
}

/** 多维表格通用定位（用于记忆表等扩展表） */
export interface BitableTableRef {
  appToken: string;
  tableId: string;
}

/** 多维表格自动建列：fieldMap 的英文 key 对齐列名，fieldTypes 为飞书字段 type 枚举 */
export interface BitableFieldSchemaSpec {
  fieldMap: Record<string, string>;
  fieldTypes: Record<string, number>;
}

/** @deprecated 请使用 BitableFieldSchemaSpec */
export type BitableMemorySchemaSpec = BitableFieldSchemaSpec;

export interface FeishuBitableFieldItem {
  field_id: string;
  field_name: string;
  type: number;
}

export interface FeishuBitableFieldListResponse {
  code: number;
  msg: string;
  data?: {
    items?: FeishuBitableFieldItem[];
    page_token?: string;
    has_more?: boolean;
  };
}

export interface FeishuBitableCreateFieldResponse {
  code: number;
  msg: string;
  data?: {
    field?: {
      field_id: string;
    };
  };
}

export interface FeishuBitableRecordItem {
  record_id: string;
  fields: Record<string, unknown>;
}

export interface FeishuBitableSearchResponse {
  code: number;
  msg: string;
  data?: {
    items?: FeishuBitableRecordItem[];
    page_token?: string;
    has_more?: boolean;
    total?: number;
  };
}

// ============================================
// 轻量记忆模块（飞书多维表格）
// ============================================

export enum WorkMode {
  ONSITE = 'onsite',
  HYBRID = 'hybrid',
  REMOTE = 'remote',
}

export enum JobType {
  FULL_TIME = 'full_time',
  INTERN = 'intern',
  PART_TIME = 'part_time',
  CONTRACT = 'contract',
}

export enum SeniorityLevel {
  JUNIOR = 'junior',
  MID = 'mid',
  SENIOR = 'senior',
  LEAD = 'lead',
  UNKNOWN = 'unknown',
}

export enum MemoryDecision {
  APPLY_NOW = 'apply_now',
  PREPARE_THEN_APPLY = 'prepare_then_apply',
  SKIP = 'skip',
}

export enum SimilarityBucket {
  HIGH = 'high',
  MEDIUM = 'medium',
  LOW = 'low',
}

export enum ProcessingStatus {
  SUCCESS = 'success',
  PARTIAL = 'partial',
  FAILED = 'failed',
}

export enum MemoryPeriodKey {
  ROLLING_30D = 'rolling_30d',
  ROLLING_90D = 'rolling_90d',
  ALL_TIME = 'all_time',
}

export interface UserProfileMemory {
  user_id: string;
  profile_version: number;
  target_roles?: string[];
  target_industries?: string[];
  preferred_cities?: string[];
  work_mode?: WorkMode;
  years_of_experience?: number;
  seniority_preference?: SeniorityLevel;
  core_skill_tags?: string[];
  weak_skill_tags?: string[];
  certifications?: string;
  resume_focus_summary?: string;
  constraints_summary?: string;
  last_active_at?: number;
  updated_at: number;
}

export interface JobRecordMemory {
  job_record_id: string;
  user_id: string;
  job_date: number;
  company_name?: string;
  job_title: string;
  location?: string;
  job_type?: JobType;
  seniority?: SeniorityLevel;
  skill_tags: string[];
  matched_skill_tags?: string[];
  gap_skill_tags?: string[];
  fit_score?: number;
  decision?: MemoryDecision;
  decision_reason_summary?: string;
  resume_advice_summary?: string;
  interview_focus_tags?: string[];
  similarity_bucket?: SimilarityBucket;
  similar_job_refs_json?: string;
  jd_fingerprint: string;
  processing_status: ProcessingStatus;
  error_code?: string;
  error_message?: string;
  created_at: number;
  updated_at: number;
}

export interface MemorySummaryRecord {
  summary_id: string;
  user_id: string;
  period_key: MemoryPeriodKey;
  computed_at: number;
  source_record_count: number;
  top_target_role_tags?: string[];
  top_skill_gap_tags?: string[];
  top_strength_tags?: string[];
  weak_points_summary?: string;
  recent_similar_job_advice?: string;
  action_plan_summary?: string;
  evidence_job_ids_json?: string;
  summary_version: number;
  updated_at: number;
}

/** 编排 / Prompt 使用的聚合记忆上下文 */
export interface MemoryContextForJobAnalysis {
  profile: UserProfileMemory | null;
  recent_job_records: JobRecordMemory[];
  summary: MemorySummaryRecord | null;
  /** 与当前 JD 技能交叠的历史岗位；无技能标签或未配置时为空数组 */
  similar_job_records: JobRecordMemory[];
}

export type SaveJobRecordInput = Omit<JobRecordMemory, 'created_at' | 'updated_at'> & {
  created_at?: number;
  updated_at?: number;
};

/** 本次 JD 处理完成后刷新记忆（编排入参） */
export interface RefreshMemoryAfterJobInput {
  userId: string;
  jobRecord: SaveJobRecordInput;
  /** 当前 JD 技能标签，用于相似岗位与摘要归纳 */
  jdSkillTags?: string[];
}

export interface ServiceResult {
  success: boolean;
  error?: string;
  recordId?: string;
}

export interface RefreshMemoryAfterJobResult {
  jobRecord: ServiceResult;
  summary: ServiceResult;
  profileTouch: ServiceResult;
}

export interface UpdateDerivedMemoryInput {
  user_profile_upsert?: Partial<Omit<UserProfileMemory, 'user_id'>> & Pick<UserProfileMemory, 'user_id'>;
  memory_summary_upsert?: Partial<Omit<MemorySummaryRecord, 'summary_id' | 'user_id' | 'period_key'>> &
    Pick<MemorySummaryRecord, 'summary_id' | 'user_id' | 'period_key'>;
}

/** 记忆表 upsertUserProfile 入参（必须带 user_id） */
export type UpsertUserProfileInput = Partial<Omit<UserProfileMemory, 'user_id'>> & Pick<UserProfileMemory, 'user_id'>;

export interface MemoryBitableUpsertResult {
  recordId: string;
  created: boolean;
}

export interface FindRecentJobRecordsOptions {
  /** 默认取 constants 中 MEMORY_RECENT_JOB_RECORDS_LIMIT */
  limit?: number;
}

export interface FindSimilarJobRecordsParams {
  userId: string;
  /** 当前 JD / 画像上的技能标签，用于与历史 skill_tags 求交叠 */
  skillTags: string[];
  /** 返回条数上限，默认 constants.MEMORY_CONTEXT_SIMILAR_JOBS_N */
  limit?: number;
  /** 参与粗排池大小，默认 constants.MEMORY_RECENT_JOB_RECORDS_LIMIT */
  recentPoolSize?: number;
}

export interface GetMemorySummaryOptions {
  periodKey?: MemoryPeriodKey;
  /**
   * 未传 periodKey 时：true 表示按 rolling_30d → all_time → rolling_90d 依次尝试
   * @default true
   */
  fallback?: boolean;
}

export interface FeishuTaskResponse {
  code: number;
  msg: string;
  data?: {
    task?: {
      guid: string;
    };
  };
}

export interface FeishuDocResponse {
  code: number;
  msg: string;
  data?: {
    document?: {
      document_id: string;
      title: string;
    };
    objToken?: string;
  };
}
