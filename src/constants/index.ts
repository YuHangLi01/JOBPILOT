// ============================================
// 业务常量
// ============================================

/** JD 文本最小有效长度 */
export const JD_MIN_LENGTH = 50;

/** JD 文本最大长度（防滥用） */
export const JD_MAX_LENGTH = 10000;

/** 默认投递状态 */
export const DEFAULT_STATUS = '待投递';

/** 默认来源 */
export const DEFAULT_SOURCE = '飞书聊天输入';

/** 任务默认截止天数 */
export const TASK_DUE_DAYS = 2;

/** 飞书 API 基地址 */
export const FEISHU_API_BASE = 'https://open.feishu.cn/open-apis';

/** 已处理事件 ID 缓存大小（简易去重） */
export const EVENT_ID_CACHE_SIZE = 500;

/** 飞书消息事件类型 */
export const FEISHU_EVENT_TYPE_MESSAGE = 'im.message.receive_v1';

/** 多维表格字段映射（字段名 → 表头显示名） */
export const BITABLE_FIELD_MAP: Record<string, string> = {
  company_name: '公司名称',
  job_title: '岗位名称',
  location: '工作地点',
  seniority: '级别要求',
  key_skills: '核心技能',
  jd_summary: '岗位总结',
  resume_suggestions: '简历建议',
  interview_questions: '面试题',
  status: '投递状态',
  created_at: '创建时间',
  source: '来源',
};
