import { createLogger } from './logger';

const log = createLogger('Retry');

/**
 * 通用重试包装器
 * @param fn 要执行的异步函数
 * @param maxRetries 最大重试次数
 * @param delayMs 重试间隔（毫秒）
 * @param label 标签（用于日志）
 */
export async function withRetry<T>(
  fn: () => Promise<T>,
  maxRetries: number = 2,
  delayMs: number = 1000,
  label: string = 'operation',
): Promise<T> {
  let lastError: Error | undefined;

  for (let attempt = 1; attempt <= maxRetries + 1; attempt++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      if (attempt <= maxRetries) {
        log.warn(`${label} 第 ${attempt} 次失败，${delayMs}ms 后重试`, lastError.message);
        await sleep(delayMs);
      }
    }
  }

  log.error(`${label} 在 ${maxRetries + 1} 次尝试后仍然失败`, lastError?.message);
  throw lastError;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
