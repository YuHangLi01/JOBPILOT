import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { PythonAgentError } from './errors';
import type { JdRoutingResponse } from './types';

// vi.hoisted ensures these are available when vi.mock factory runs (which is hoisted to top of file)
const { mockPost, mockGet } = vi.hoisted(() => ({
  mockPost: vi.fn(),
  mockGet: vi.fn(),
}));

vi.mock('axios', async (importOriginal) => {
  const actual = await importOriginal<typeof import('axios')>();
  return {
    ...actual,
    default: {
      ...actual.default,
      create: vi.fn(() => ({
        post: mockPost,
        get: mockGet,
      })),
      isAxiosError: actual.default.isAxiosError,
    },
  };
});

vi.mock('../../config', () => ({
  config: {
    pythonAgent: {
      url: 'http://localhost:8000',
      timeoutMs: 30000,
      usePythonAgent: false,
      internalSecret: '',
    },
  },
}));

const MOCK_JD_ROUTING_RESPONSE: JdRoutingResponse = {
  jd_parsed: {
    company_name: 'TestCo',
    job_title: 'Engineer',
    location: 'Beijing',
    job_type: 'full_time',
    responsibilities: [],
    requirements: [],
    preferred_qualifications: [],
    key_skills: ['TypeScript'],
    seniority: 'mid',
    summary: 'A test job',
  },
  job_summary: 'Good opportunity',
  resume_suggestions: ['Highlight TypeScript skills'],
  interview_questions: [
    { question: 'Tell me about yourself', intent: 'background', answer_tips: ['Be concise'] },
  ],
  bitable_result: { success: true, record_id: 'rec123' },
  task_result: { success: true, task_id: 'task456' },
  document_result: { success: true, doc_url: 'https://docs.feishu.cn/xxx' },
};

describe('PythonAgentClient', () => {
  // Import after mocks are in place
  let client: import('./client').PythonAgentClient;

  beforeEach(async () => {
    vi.clearAllMocks();
    const { PythonAgentClient } = await import('./client');
    client = new PythonAgentClient();
  });

  it('正常返回：postJdRouting 返回正确结构', async () => {
    mockPost.mockResolvedValueOnce({ data: MOCK_JD_ROUTING_RESPONSE });

    const result = await client.postJdRouting({ jd_text: 'Software Engineer at TestCo' });

    expect(result.job_summary).toBe('Good opportunity');
    expect(result.jd_parsed.company_name).toBe('TestCo');
    expect(result.bitable_result.success).toBe(true);
    expect(mockPost).toHaveBeenCalledOnce();

    // 确认 request_id 被自动注入到 header
    const [, , callConfig] = mockPost.mock.calls[0];
    expect(callConfig?.headers?.['X-Request-Id']).toBeDefined();
  });

  it('超时：axios ECONNABORTED 应抛出 PythonAgentError(code=TIMEOUT, retryable=true)', async () => {
    const timeoutError = new Error('timeout of 30000ms exceeded');
    Object.assign(timeoutError, { code: 'ECONNABORTED', isAxiosError: true, config: {}, response: undefined, request: {} });
    vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
    mockPost.mockRejectedValueOnce(timeoutError);

    await expect(
      client.postJdRouting({ jd_text: 'some jd' }),
    ).rejects.toMatchObject({
      name: 'PythonAgentError',
      code: 'TIMEOUT',
      retryable: true,
    });
  });

  it('HTTP 4xx：应抛出 PythonAgentError(code=HTTP_4XX, retryable=false)', async () => {
    const error400 = new Error('Request failed with status code 400');
    Object.assign(error400, { isAxiosError: true, code: undefined, config: {}, response: { status: 400, data: { detail: 'bad request' } }, request: {} });
    vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
    mockPost.mockRejectedValueOnce(error400);

    await expect(
      client.postJdRouting({ jd_text: 'some jd' }),
    ).rejects.toMatchObject({
      name: 'PythonAgentError',
      code: 'HTTP_4XX',
      retryable: false,
      statusCode: 400,
    });
  });

  it('HTTP 5xx：应抛出 PythonAgentError(code=HTTP_5XX, retryable=true)', async () => {
    const error500 = new Error('Request failed with status code 500');
    Object.assign(error500, { isAxiosError: true, code: undefined, config: {}, response: { status: 500, data: { detail: 'internal server error' } }, request: {} });
    vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
    mockPost.mockRejectedValueOnce(error500);

    await expect(
      client.postJdRouting({ jd_text: 'some jd' }),
    ).rejects.toMatchObject({
      name: 'PythonAgentError',
      code: 'HTTP_5XX',
      retryable: true,
      statusCode: 500,
    });
  });

  it('PythonAgentError 正确包装：错误实例应为 PythonAgentError', async () => {
    const error503 = new Error('Service Unavailable');
    Object.assign(error503, { isAxiosError: true, code: undefined, config: {}, response: { status: 503, data: null }, request: {} });
    vi.spyOn(axios, 'isAxiosError').mockReturnValueOnce(true);
    mockPost.mockRejectedValueOnce(error503);

    try {
      await client.postJdRouting({ jd_text: 'some jd' });
      expect.fail('应该抛出 PythonAgentError');
    } catch (err) {
      expect(err).toBeInstanceOf(PythonAgentError);
      expect((err as PythonAgentError).code).toBe('HTTP_5XX');
    }
  });
});
