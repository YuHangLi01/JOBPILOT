import dotenv from 'dotenv';
dotenv.config();

function requireEnv(key: string, fallback?: string): string {
  const val = process.env[key] ?? fallback;
  if (!val) {
    throw new Error(`缺少必要环境变量: ${key}，请检查 .env 文件`);
  }
  return val;
}

const feishuBitableAppToken = requireEnv('FEISHU_BITABLE_APP_TOKEN');

export const config = {
  /** 服务端口 */
  port: parseInt(process.env.PORT || '3000', 10),
  nodeEnv: process.env.NODE_ENV || 'development',

  /** 飞书应用 */
  feishu: {
    appId: requireEnv('FEISHU_APP_ID'),
    appSecret: requireEnv('FEISHU_APP_SECRET'),
    verificationToken: requireEnv('FEISHU_VERIFICATION_TOKEN'),
    encryptKey: process.env.FEISHU_ENCRYPT_KEY || '',
    bitableAppToken: feishuBitableAppToken,
    bitableTableId: requireEnv('FEISHU_BITABLE_TABLE_ID'),
    /** 求职记忆三张表：与主分析表可共用同一 app，仅 table 不同 */
    memoryBitableAppToken: process.env.FEISHU_MEMORY_BITABLE_APP_TOKEN || feishuBitableAppToken,
    memoryUserProfileTableId: process.env.FEISHU_MEMORY_USER_PROFILE_TABLE_ID || '',
    memoryJobRecordsTableId: process.env.FEISHU_MEMORY_JOB_RECORDS_TABLE_ID || '',
    memorySummaryTableId: process.env.FEISHU_MEMORY_SUMMARY_TABLE_ID || '',
    docFolderToken: process.env.FEISHU_DOC_FOLDER_TOKEN || '',
  },

  /** 大模型 */
  llm: {
    apiBaseUrl: requireEnv('LLM_API_BASE_URL', 'https://api.openai.com/v1'),
    apiKey: requireEnv('LLM_API_KEY'),
    model: process.env.LLM_MODEL || 'gpt-4o',
    timeout: parseInt(process.env.LLM_TIMEOUT || '30000', 10),
    maxRetries: parseInt(process.env.LLM_MAX_RETRIES || '2', 10),
  },

  /** 日志 */
  logLevel: process.env.LOG_LEVEL || 'info',
} as const;
