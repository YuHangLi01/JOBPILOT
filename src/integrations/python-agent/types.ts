/**
 * Python Agent API 类型
 *
 * 此文件由 openapi-typescript 从 contracts/openapi.json 自动生成后 re-export。
 * 禁止手工定义重复接口——如需修改类型，请：
 *   1. 修改 Python Agent 的 Pydantic Schema
 *   2. 在项目根目录运行 `make contracts`（或 `npm run gen:types`）
 *   3. 将 generated.ts 和 openapi.json 的变更一起提交
 */

import type { components } from './generated';

// ── JD 路由 ────────────────────────────────────────────────────────────────
export type JdRoutingRequest = components['schemas']['JDRoutingRequest'];
export type JdRoutingResponse = components['schemas']['JDRoutingResponse'];
export type JDClassification = components['schemas']['JDClassification'];
export type JDRoutingResults = components['schemas']['JDRoutingResults'];
export type ResumeAdviceItem = components['schemas']['ResumeAdviceItem'];
export type UserContext = components['schemas']['UserContext'];
export type ResponseMetadata = components['schemas']['ResponseMetadata'];

// ── 面试 ───────────────────────────────────────────────────────────────────
export type StartInterviewRequest = components['schemas']['InterviewStartRequest'];
export type StartInterviewResponse = components['schemas']['InterviewStartResponse'];
export type ResumeInterviewRequest = components['schemas']['InterviewResumeRequest'];
export type ResumeInterviewResponse = components['schemas']['InterviewResumeResponse'];
export type GetInterviewStatusResponse = components['schemas']['InterviewStatusResponse'];
export type NextAction = components['schemas']['NextAction'];
export type InterviewReport = components['schemas']['InterviewReport'];
export type StageScore = components['schemas']['StageScore'];

// ── 面试问题（在 JD 路由结果与面试两处使用） ──────────────────────────────
export type InterviewQuestion = components['schemas']['InterviewQuestion'];

// ── 公共 ───────────────────────────────────────────────────────────────────
export type ErrorDetail = components['schemas']['HTTPValidationError'];

// ── 健康检查（Python Agent 响应，无 Schema，直接用 inline 类型） ───────────
export interface PythonAgentHealthResponse {
  status: 'ok' | 'degraded' | 'error';
  version?: string;
  uptime_seconds?: number;
}

// ── 兼容旧调用（GetInterviewStatusRequest 是 path param，不是 request body）─
export interface GetInterviewStatusRequest {
  session_id: string;
}
