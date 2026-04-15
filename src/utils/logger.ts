/**
 * 轻量级日志工具
 * 生产项目可替换为 pino / winston
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LEVEL_PRIORITY: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const currentLevel: LogLevel = (process.env.LOG_LEVEL as LogLevel) || 'info';

function shouldLog(level: LogLevel): boolean {
  return LEVEL_PRIORITY[level] >= LEVEL_PRIORITY[currentLevel];
}

function formatMsg(level: LogLevel, module: string, msg: string, meta?: unknown): string {
  const ts = new Date().toISOString();
  const base = `[${ts}] [${level.toUpperCase()}] [${module}] ${msg}`;
  if (meta !== undefined) {
    const metaStr = typeof meta === 'string' ? meta : JSON.stringify(meta, null, 2);
    return `${base}\n${metaStr}`;
  }
  return base;
}

export function createLogger(module: string) {
  return {
    debug(msg: string, meta?: unknown) {
      if (shouldLog('debug')) console.debug(formatMsg('debug', module, msg, meta));
    },
    info(msg: string, meta?: unknown) {
      if (shouldLog('info')) console.log(formatMsg('info', module, msg, meta));
    },
    warn(msg: string, meta?: unknown) {
      if (shouldLog('warn')) console.warn(formatMsg('warn', module, msg, meta));
    },
    error(msg: string, meta?: unknown) {
      if (shouldLog('error')) console.error(formatMsg('error', module, msg, meta));
    },
  };
}
