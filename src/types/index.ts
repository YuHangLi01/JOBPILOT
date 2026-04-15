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
