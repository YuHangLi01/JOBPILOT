import axios, { AxiosInstance, isAxiosError } from 'axios';
import { v4 as uuidv4 } from 'uuid';
import { config } from '../../config';
import { PythonAgentError } from './errors';
import type {
  JdRoutingRequest,
  JdRoutingResponse,
  StartInterviewRequest,
  StartInterviewResponse,
  ResumeInterviewRequest,
  ResumeInterviewResponse,
  GetInterviewStatusRequest,
  GetInterviewStatusResponse,
} from './types';

function createAxiosInstance(): AxiosInstance {
  return axios.create({
    baseURL: config.pythonAgent.url,
    timeout: config.pythonAgent.timeoutMs,
    headers: { 'Content-Type': 'application/json' },
  });
}

/**
 * 统一将 axios 错误转换为 PythonAgentError。
 */
function wrapError(err: unknown): never {
  if (isAxiosError(err)) {
    if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT' || err.message?.includes('timeout')) {
      throw new PythonAgentError({
        message: `Python Agent request timed out: ${err.message}`,
        code: 'TIMEOUT',
        retryable: true,
      });
    }

    if (err.response) {
      const status = err.response.status;
      const isClient = status >= 400 && status < 500;
      throw new PythonAgentError({
        message: `Python Agent responded with HTTP ${status}`,
        code: isClient ? 'HTTP_4XX' : 'HTTP_5XX',
        retryable: !isClient,
        statusCode: status,
        partialResults: err.response.data,
      });
    }

    throw new PythonAgentError({
      message: `Python Agent network error: ${err.message}`,
      code: 'NETWORK',
      retryable: true,
    });
  }

  throw err;
}

export class PythonAgentClient {
  private readonly http: AxiosInstance;

  constructor() {
    this.http = createAxiosInstance();
  }

  /**
   * JD 路由：触发完整的 JD 分析与飞书生态写入流程。
   * JDRoutingRequest.request_id 由调用方或此处自动填充。
   */
  async postJdRouting(
    req: Omit<JdRoutingRequest, 'request_id'> & { request_id?: string },
  ): Promise<JdRoutingResponse> {
    const payload: JdRoutingRequest = {
      ...req,
      request_id: req.request_id ?? uuidv4(),
    };
    try {
      const res = await this.http.post<JdRoutingResponse>('/api/v1/agent/jd-routing', payload, {
        headers: { 'X-Request-Id': payload.request_id },
      });
      return res.data;
    } catch (err) {
      wrapError(err);
    }
  }

  /**
   * 开始一轮模拟面试会话。
   * StartInterviewRequest 使用 thread_id 标识会话，无 request_id 字段。
   */
  async startInterview(req: StartInterviewRequest): Promise<StartInterviewResponse> {
    const requestId = uuidv4();
    try {
      const res = await this.http.post<StartInterviewResponse>(
        '/api/v1/agent/interview/start',
        req,
        { headers: { 'X-Request-Id': requestId } },
      );
      return res.data;
    } catch (err) {
      wrapError(err);
    }
  }

  /**
   * 继续面试会话，提交本轮回答并获取下一题。
   * ResumeInterviewRequest 使用 thread_id + user_input，无 request_id 字段。
   */
  async resumeInterview(req: ResumeInterviewRequest): Promise<ResumeInterviewResponse> {
    const requestId = uuidv4();
    try {
      const res = await this.http.post<ResumeInterviewResponse>(
        '/api/v1/agent/interview/resume',
        req,
        { headers: { 'X-Request-Id': requestId } },
      );
      return res.data;
    } catch (err) {
      wrapError(err);
    }
  }

  /**
   * 查询面试会话当前状态。
   */
  async getInterviewStatus(req: GetInterviewStatusRequest): Promise<GetInterviewStatusResponse> {
    try {
      const res = await this.http.get<GetInterviewStatusResponse>(
        `/api/v1/agent/interview/${req.session_id}/status`,
      );
      return res.data;
    } catch (err) {
      wrapError(err);
    }
  }
}

export const pythonAgentClient = new PythonAgentClient();
