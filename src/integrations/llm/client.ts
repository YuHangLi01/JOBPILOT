import axios, { AxiosInstance } from 'axios';
import { config } from '../../config';
import { createLogger } from '../../utils/logger';
import { withRetry } from '../../utils/retry';
import type { LLMMessage, LLMResponse } from '../../types';

const log = createLogger('LLMClient');

/**
 * 统一大模型调用客户端
 * 兼容 OpenAI / 火山方舟 / DeepSeek / 通义千问等 OpenAI 兼容接口
 */
export class LLMClient {
  private http: AxiosInstance;
  private model: string;
  private maxRetries: number;

  constructor() {
    this.model = config.llm.model;
    this.maxRetries = config.llm.maxRetries;

    this.http = axios.create({
      baseURL: config.llm.apiBaseUrl,
      timeout: config.llm.timeout,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${config.llm.apiKey}`,
      },
    });
  }

  /**
   * 发送聊天补全请求
   */
  async chat(messages: LLMMessage[], temperature: number = 0.3): Promise<LLMResponse> {
    return withRetry(
      async () => {
        log.info(`调用 LLM [${this.model}]，消息数: ${messages.length}`);
        log.debug('请求内容', messages);

        const response = await this.http.post('/chat/completions', {
          model: this.model,
          messages,
          temperature,
          max_tokens: 4096,
        });

        const data = response.data;
        const content = data.choices?.[0]?.message?.content || '';

        log.info('LLM 返回成功', {
          contentLength: content.length,
          usage: data.usage,
        });
        log.debug('LLM 原始响应', content);

        return {
          content,
          usage: data.usage,
        };
      },
      this.maxRetries,
      1500,
      'LLM Chat',
    );
  }

  /**
   * 发送请求并期望返回 JSON，自动解析
   */
  async chatJSON<T>(
    messages: LLMMessage[],
    parser: (raw: string) => T | null,
    label: string = 'LLM JSON',
  ): Promise<T> {
    const resp = await this.chat(messages);
    const raw = resp.content;

    // 尝试清理 markdown code block
    const cleaned = raw
      .replace(/^```(?:json)?\s*/i, '')
      .replace(/\s*```$/i, '')
      .trim();

    const parsed = parser(cleaned);
    if (parsed === null) {
      log.error(`${label} 返回内容无法解析为目标格式`, cleaned);
      throw new Error(`${label} 返回格式异常，无法解析`);
    }

    return parsed;
  }
}

/** 单例 */
let instance: LLMClient | null = null;

export function getLLMClient(): LLMClient {
  if (!instance) {
    instance = new LLMClient();
  }
  return instance;
}
