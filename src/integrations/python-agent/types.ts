/**
 * Python Agent HTTP API 类型定义
 *
 * 此文件为手写占位版本，下周将由 openapi-typescript 自动生成替换。
 * 字段命名与 Python Agent 接口约定保持 snake_case 风格。
 */

import type { JDParsed, InterviewQuestion } from '../../types';

// ============================================================
// 1. JD 路由（对应编排器主入口）
// ============================================================

export interface JdRoutingRequest {
  jd_text: string;
  user_id?: string;
  request_id: string;
}

export interface JdRoutingResponse {
  jd_parsed: JDParsed;
  job_summary: string;
  resume_suggestions: string[];
  interview_questions: InterviewQuestion[];
  bitable_result: {
    success: boolean;
    record_id?: string;
    error?: string;
  };
  task_result: {
    success: boolean;
    task_id?: string;
    error?: string;
  };
  document_result: {
    success: boolean;
    doc_url?: string;
    error?: string;
  };
}

// ============================================================
// 2. 开始面试会话
// ============================================================

export interface StartInterviewRequest {
  user_id: string;
  jd_text: string;
  request_id: string;
}

export interface StartInterviewResponse {
  session_id: string;
  first_question: string;
  status: 'started';
}

// ============================================================
// 3. 继续面试会话
// ============================================================

export interface ResumeInterviewRequest {
  session_id: string;
  user_answer: string;
  request_id: string;
}

export interface ResumeInterviewResponse {
  session_id: string;
  next_question?: string;
  feedback?: string;
  status: 'in_progress' | 'completed';
}

// ============================================================
// 4. 查询面试状态
// ============================================================

export interface GetInterviewStatusRequest {
  session_id: string;
}

export interface GetInterviewStatusResponse {
  session_id: string;
  status: 'started' | 'in_progress' | 'completed' | 'error';
  progress?: number;
  total_questions?: number;
}

// ============================================================
// 5. 健康检查
// ============================================================

export interface PythonAgentHealthResponse {
  status: 'ok' | 'degraded' | 'error';
  version?: string;
  uptime_seconds?: number;
}
