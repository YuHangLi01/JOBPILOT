import axios from 'axios';
import { feishuAuth } from './auth';
import { config } from '../../config';
import {
  FEISHU_API_BASE,
  BITABLE_FIELD_MAP,
  BITABLE_MAIN_SCHEMA,
  MEMORY_CONTEXT_SIMILAR_JOBS_N,
  MEMORY_JOB_RECORDS_FIELD_MAP,
  MEMORY_JOB_RECORDS_SCHEMA,
  MEMORY_RECENT_JOB_RECORDS_LIMIT,
  MEMORY_SUMMARY_FIELD_MAP,
  MEMORY_SUMMARY_SCHEMA,
  MEMORY_USER_PROFILE_FIELD_MAP,
  MEMORY_USER_PROFILE_SCHEMA,
} from '../../constants';
import { createLogger } from '../../utils/logger';
import type {
  BitableFieldSchemaSpec,
  BitableRecord,
  BitableTableRef,
  FeishuBitableCreateFieldResponse,
  FeishuBitableFieldItem,
  FeishuBitableFieldListResponse,
  FeishuBitableRecordItem,
  FeishuBitableResponse,
  FeishuBitableSearchResponse,
  FindRecentJobRecordsOptions,
  FindSimilarJobRecordsParams,
  GetMemorySummaryOptions,
  JobRecordMemory,
  MemoryBitableUpsertResult,
  MemorySummaryRecord,
  UpsertUserProfileInput,
  UserProfileMemory,
} from '../../types';
import { MemoryPeriodKey } from '../../types';
import {
  buildTextEqFilter,
  buildUserAndPeriodFilter,
  encodeMemoryFields,
  parseJobRecord,
  parseMemorySummary,
  parseUserProfile,
  rowKeysToObject,
} from './bitable-memory.codec';

const log = createLogger('FeishuBitable');
const memoryLog = createLogger('FeishuMemoryBitable');

/**
 * 飞书多维表格服务
 *
 * 多维表格字段初始化说明：
 * 请在飞书多维表格中手动创建一个数据表，包含以下字段：
 *   - 公司名称（文本）
 *   - 岗位名称（文本）
 *   - 工作地点（文本）
 *   - 级别要求（文本）
 *   - 核心技能（文本）
 *   - 岗位总结（文本）
 *   - 简历建议（文本）
 *   - 面试题（文本）
 *   - 投递状态（单选：待投递 / 已投递 / 面试中 / 已拿 offer / 已拒绝）
 *   - 创建时间（日期）
 *   - 来源（文本）
 *
 * 配置完成后将 app_token 和 table_id 填入 .env。
 * 写入前会按 `BITABLE_MAIN_SCHEMA` 自动补全缺失列（与 README 说明一致）。
 */
export class FeishuBitableService {
  private appToken: string;
  private tableId: string;
  private upsertLocks = new Map<string, Promise<void>>();

  constructor() {
    this.appToken = config.feishu.bitableAppToken;
    this.tableId = config.feishu.bitableTableId;
  }

  /**
   * 向多维表格写入一条记录
   */
  async addRecord(record: BitableRecord): Promise<{ recordId: string }> {
    log.info('写入多维表格记录', {
      company: record.company_name,
      job: record.job_title,
    });
    const { recordId } = await this.upsertMainRecord(record);
    return { recordId };
  }

  private async withUpsertLock<T>(lockKey: string, task: () => Promise<T>): Promise<T> {
    const previous = this.upsertLocks.get(lockKey) ?? Promise.resolve();
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const current = previous.then(() => gate);
    this.upsertLocks.set(lockKey, current);

    await previous;
    try {
      return await task();
    } finally {
      release();
      if (this.upsertLocks.get(lockKey) === current) {
        this.upsertLocks.delete(lockKey);
      }
    }
  }

  async upsertRecordInTable(
    ref: BitableTableRef,
    params: {
      lockKey: string;
      filter: Record<string, unknown>;
      fields: Record<string, unknown>;
      fieldSchema?: BitableFieldSchemaSpec;
    },
  ): Promise<MemoryBitableUpsertResult> {
    return this.withUpsertLock(params.lockKey, async () => {
      const search = await this.searchRecordsInTable(
        ref,
        {
          page_size: 20,
          filter: params.filter,
        },
        params.fieldSchema,
      );
      const hit = search.items[0];
      const duplicateCount = Math.max(0, search.items.length - 1);
      if (duplicateCount > 0) {
        log.warn('检测到重复记录，更新首条并阻止继续新增', {
          tableId: ref.tableId,
          lockKey: params.lockKey,
          duplicateCount,
        });
      }
      if (hit) {
        await this.updateRecordInTable(ref, hit.record_id, params.fields, params.fieldSchema);
        return { recordId: hit.record_id, created: false, duplicateCount };
      }
      const { recordId } = await this.createRecordInTable(ref, params.fields, params.fieldSchema);
      return { recordId, created: true, duplicateCount: 0 };
    });
  }

  async upsertMainRecord(record: BitableRecord): Promise<MemoryBitableUpsertResult> {
    const ref = { appToken: this.appToken, tableId: this.tableId };
    await this.ensureBitableFieldSchema(ref, BITABLE_MAIN_SCHEMA);

    const fields: Record<string, unknown> = {};
    for (const [key, label] of Object.entries(BITABLE_FIELD_MAP)) {
      const value = record[key as keyof BitableRecord];
      fields[label] = value;
    }

    return this.upsertRecordInTable(ref, {
      lockKey: `main:${record.analysis_id}`,
      filter: buildTextEqFilter(BITABLE_FIELD_MAP.analysis_id, record.analysis_id),
      fields,
      fieldSchema: BITABLE_MAIN_SCHEMA,
    });
  }

  /**
   * 批量写入记录（预留扩展）
   */
  async addRecords(records: BitableRecord[]): Promise<void> {
    // TODO: 使用飞书批量新增接口 /bitable/v1/apps/:app_token/tables/:table_id/records/batch_create
    for (const record of records) {
      await this.upsertMainRecord(record);
    }
  }

  /**
   * 向指定多维表格新增一条记录（字段已为飞书列名 → 值）
   */
  async createRecordInTable(
    ref: BitableTableRef,
    fields: Record<string, unknown>,
    fieldSchema?: BitableFieldSchemaSpec,
  ): Promise<{ recordId: string }> {
    if (fieldSchema) {
      await this.ensureBitableFieldSchema(ref, fieldSchema);
    }
    log.info('写入多维表格（扩展表）', { tableId: ref.tableId });
    const headers = await feishuAuth.getAuthHeaders();
    const url = `${FEISHU_API_BASE}/bitable/v1/apps/${ref.appToken}/tables/${ref.tableId}/records`;
    const resp = await axios.post<FeishuBitableResponse>(url, { fields }, { headers, timeout: 15000 });
    if (resp.data.code !== 0) {
      throw new Error(`多维表格新增失败: code=${resp.data.code}, msg=${resp.data.msg}`);
    }
    const recordId = resp.data.data?.record?.record_id || 'unknown';
    return { recordId };
  }

  /**
   * 更新指定记录（部分字段）
   */
  async updateRecordInTable(
    ref: BitableTableRef,
    recordId: string,
    fields: Record<string, unknown>,
    fieldSchema?: BitableFieldSchemaSpec,
  ): Promise<void> {
    if (fieldSchema) {
      await this.ensureBitableFieldSchema(ref, fieldSchema);
    }
    log.info('更新多维表格记录', { tableId: ref.tableId, recordId });
    const headers = await feishuAuth.getAuthHeaders();
    const url = `${FEISHU_API_BASE}/bitable/v1/apps/${ref.appToken}/tables/${ref.tableId}/records/${recordId}`;
    const resp = await axios.put<FeishuBitableResponse>(url, { fields }, { headers, timeout: 15000 });
    if (resp.data.code !== 0) {
      throw new Error(`多维表格更新失败: code=${resp.data.code}, msg=${resp.data.msg}`);
    }
  }

  /**
   * 删除指定记录
   */
  async deleteRecordInTable(ref: BitableTableRef, recordId: string): Promise<void> {
    log.info('删除多维表格记录', { tableId: ref.tableId, recordId });
    const headers = await feishuAuth.getAuthHeaders();
    const url = `${FEISHU_API_BASE}/bitable/v1/apps/${ref.appToken}/tables/${ref.tableId}/records/${recordId}`;
    const resp = await axios.delete<FeishuBitableResponse>(url, { headers, timeout: 15000 });
    if (resp.data.code !== 0) {
      throw new Error(`多维表格删除失败: code=${resp.data.code}, msg=${resp.data.msg}`);
    }
  }

  /**
   * 条件检索记录（filter/sort 等直接透传飞书 search body）
   */
  /**
   * 条件检索；传入 fieldSchema 时会在检索前对齐列（缺列则自动创建，避免因缺列导致检索失败）
   */
  async searchRecordsInTable(
    ref: BitableTableRef,
    body: Record<string, unknown>,
    fieldSchema?: BitableFieldSchemaSpec,
  ): Promise<{ items: FeishuBitableRecordItem[]; page_token?: string; has_more: boolean }> {
    if (fieldSchema) {
      await this.ensureBitableFieldSchema(ref, fieldSchema);
    }
    const headers = await feishuAuth.getAuthHeaders();
    const url = `${FEISHU_API_BASE}/bitable/v1/apps/${ref.appToken}/tables/${ref.tableId}/records/search`;
    const resp = await axios.post<FeishuBitableSearchResponse>(url, body, { headers, timeout: 15000 });
    if (resp.data.code !== 0) {
      throw new Error(`多维表格检索失败: code=${resp.data.code}, msg=${resp.data.msg}`);
    }
    const data = resp.data.data;
    return {
      items: data?.items ?? [],
      page_token: data?.page_token,
      has_more: Boolean(data?.has_more),
    };
  }

  /**
   * 列出数据表全部字段（分页拉齐）
   */
  async listTableFields(ref: BitableTableRef): Promise<FeishuBitableFieldItem[]> {
    const headers = await feishuAuth.getAuthHeaders();
    const all: FeishuBitableFieldItem[] = [];
    let page_token: string | undefined;
    for (let page = 0; page < 50; page++) {
      const qs = new URLSearchParams({ page_size: '100' });
      if (page_token) qs.set('page_token', page_token);
      const url = `${FEISHU_API_BASE}/bitable/v1/apps/${ref.appToken}/tables/${ref.tableId}/fields?${qs.toString()}`;
      const resp = await axios.get<FeishuBitableFieldListResponse>(url, { headers, timeout: 15000 });
      if (resp.data.code !== 0) {
        throw new Error(`列出字段失败: code=${resp.data.code}, msg=${resp.data.msg}`);
      }
      const items = resp.data.data?.items ?? [];
      for (const raw of items) {
        const it = raw as FeishuBitableFieldItem & { name?: string };
        const field_name = it.field_name || it.name || '';
        if (it.field_id && field_name) {
          all.push({ field_id: it.field_id, field_name, type: it.type });
        }
      }
      if (!resp.data.data?.has_more || !resp.data.data.page_token) break;
      page_token = resp.data.data.page_token;
    }
    return all;
  }

  /**
   * 新增一列（记忆表对齐用；单选/多选需 property 时由 defaultFieldPropertyForType 填充占位选项）
   */
  async createTableField(
    ref: BitableTableRef,
    field_name: string,
    type: number,
    property?: unknown,
  ): Promise<void> {
    const headers = await feishuAuth.getAuthHeaders();
    const url = `${FEISHU_API_BASE}/bitable/v1/apps/${ref.appToken}/tables/${ref.tableId}/fields`;
    const payload: Record<string, unknown> = { field_name, type };
    if (property !== undefined) payload.property = property;
    const resp = await axios.post<FeishuBitableCreateFieldResponse>(url, payload, { headers, timeout: 15000 });
    if (resp.data.code === 0) return;
    const msg = resp.data.msg || '';
    if (
      msg.includes('同名') ||
      msg.includes('已存在') ||
      msg.includes('duplicat') ||
      msg.includes('already exists') ||
      msg.includes('FieldName')
    ) {
      log.info('字段已存在或重名，跳过创建', { field_name, code: resp.data.code, msg });
      return;
    }
    throw new Error(`新增字段失败: code=${resp.data.code}, msg=${resp.data.msg}`);
  }

  /**
   * 按 schema 补全缺失列；失败仅打日志，不抛错（由上层检索/写入自行降级）
   */
  async ensureBitableFieldSchema(ref: BitableTableRef, spec: BitableFieldSchemaSpec): Promise<void> {
    try {
      const items = await this.listTableFields(ref);
      const existing = new Set(items.map((f) => f.field_name.trim()).filter(Boolean));
      for (const [enKey, label] of Object.entries(spec.fieldMap)) {
        const name = label.trim();
        if (!name || existing.has(name)) continue;
        const t = spec.fieldTypes[enKey] ?? 1;
        const prop = defaultFieldPropertyForType(t);
        try {
          await this.createTableField(ref, name, t, prop);
          existing.add(name);
          log.info('记忆表已自动补列', { tableId: ref.tableId, field_name: name, type: t });
        } catch (err) {
          log.warn('记忆表单列创建失败，跳过该列', {
            field_name: name,
            err: err instanceof Error ? err.message : err,
          });
        }
      }
    } catch (err) {
      log.warn('记忆表字段对齐失败（不阻塞）', err instanceof Error ? err.message : err);
    }
  }
}

function defaultFieldPropertyForType(type: number): unknown | undefined {
  if (type === 3) return { options: [{ name: '—' }] };
  if (type === 4) return { options: [{ name: '—' }] };
  return undefined;
}

export const feishuBitableService = new FeishuBitableService();

// ---------------------------------------------------------------------------
// 求职记忆多维表格（三张表）— 领域 API，内部仍走 FeishuBitableService 通用 CRUD
// ---------------------------------------------------------------------------

function isTransientNetworkError(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  const status = err.response?.status;
  if (status === 429) return true;
  if (status !== undefined && status >= 500) return true;
  // 无 HTTP 响应：超时、DNS、断连等
  return err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT' || !err.response;
}

/**
 * 飞书多维表格「求职记忆」封装
 *
 * 数据映射：TS 模型字段（snake_case）↔ 飞书列名见 `constants` 中 MEMORY_*_FIELD_MAP。
 * 标签类数组写入前会 `joinArrayValues` 为「、」文本，以兼容自动补列时的「文本」列；读出仍兼容多选数组与纯文本。
 * 日期时间：写入 number（毫秒时间戳）；读出按 number 解析。
 * JSON 串字段（如相似岗位引用）：写入 JSON 字符串，避免嵌套类型写入受限。
 */
export class FeishuMemoryBitableService {
  constructor(private readonly bitable: FeishuBitableService) {}

  private isConfigured(): boolean {
    const f = config.feishu;
    return Boolean(f.memoryUserProfileTableId && f.memoryJobRecordsTableId && f.memorySummaryTableId);
  }

  private assertConfigured(): void {
    if (!this.isConfigured()) {
      throw new Error('[FeishuMemoryBitable] 未配置 FEISHU_MEMORY_*_TABLE_ID，无法写入记忆表');
    }
  }

  private profileRef(): BitableTableRef {
    return {
      appToken: config.feishu.memoryBitableAppToken,
      tableId: config.feishu.memoryUserProfileTableId,
    };
  }

  private jobRef(): BitableTableRef {
    return {
      appToken: config.feishu.memoryBitableAppToken,
      tableId: config.feishu.memoryJobRecordsTableId,
    };
  }

  private summaryRef(): BitableTableRef {
    return {
      appToken: config.feishu.memoryBitableAppToken,
      tableId: config.feishu.memorySummaryTableId,
    };
  }

  /** 仅对网络类 / 5xx / 429 做有限次重试；飞书业务 code≠0 不重试 */
  private async withTransientRetry<T>(label: string, fn: () => Promise<T>): Promise<T> {
    const delaysMs = [500, 1000];
    let lastErr: unknown;
    for (let attempt = 0; attempt <= delaysMs.length; attempt++) {
      try {
        return await fn();
      } catch (err) {
        lastErr = err;
        if (attempt < delaysMs.length && isTransientNetworkError(err)) {
          memoryLog.warn(`${label} 可重试错误，${delaysMs[attempt]}ms 后重试`, err instanceof Error ? err.message : err);
          await new Promise((r) => setTimeout(r, delaysMs[attempt]));
          continue;
        }
        throw err;
      }
    }
    throw lastErr;
  }

  private static normTagSet(tags: string[]): Set<string> {
    return new Set(tags.map((t) => t.trim().toLowerCase()).filter(Boolean));
  }

  private static overlapScore(job: JobRecordMemory, query: Set<string>): number {
    if (!job.skill_tags?.length || query.size === 0) return 0;
    const jobSet = new Set(job.skill_tags.map((t) => t.trim().toLowerCase()).filter(Boolean));
    let n = 0;
    for (const t of query) {
      if (jobSet.has(t)) n += 1;
    }
    return n;
  }

  private static rankSimilarJobs(
    pool: JobRecordMemory[],
    skillTags: string[],
    limit: number,
  ): JobRecordMemory[] {
    const q = FeishuMemoryBitableService.normTagSet(skillTags);
    const scored = pool.map((j) => ({
      j,
      s: FeishuMemoryBitableService.overlapScore(j, q),
    }));
    const positive = scored.filter((x) => x.s > 0).sort((a, b) => b.s - a.s || b.j.job_date - a.j.job_date);
    const zero = scored.filter((x) => x.s === 0).sort((a, b) => b.j.job_date - a.j.job_date);
    return [...positive, ...zero].slice(0, limit).map((x) => x.j);
  }

  private mergeUserProfile(existing: UserProfileMemory | null, patch: UpsertUserProfileInput, now: number): UserProfileMemory {
    const base = existing ?? {
      user_id: patch.user_id,
      profile_version: 1,
      updated_at: now,
    };
    return {
      ...base,
      ...patch,
      user_id: patch.user_id,
      profile_version: patch.profile_version ?? existing?.profile_version ?? 1,
      updated_at: now,
    };
  }

  private mergeMemorySummary(existing: MemorySummaryRecord | null, row: MemorySummaryRecord): MemorySummaryRecord {
    if (!existing) return row;
    return { ...existing, ...row };
  }

  /**
   * 按用户 ID 读取单条画像（无表或未命中返回 null）
   */
  async getUserProfileByUserId(userId: string): Promise<UserProfileMemory | null> {
    if (!userId.trim() || !this.isConfigured()) return null;
    const ref = this.profileRef();
    const res = await this.withTransientRetry('memory.getUserProfile', () =>
      this.bitable.searchRecordsInTable(
        ref,
        {
          page_size: 1,
          filter: buildTextEqFilter(MEMORY_USER_PROFILE_FIELD_MAP.user_id, userId),
        },
        MEMORY_USER_PROFILE_SCHEMA,
      ),
    );
    const raw = res.items[0]?.fields
      ? rowKeysToObject(MEMORY_USER_PROFILE_FIELD_MAP, res.items[0].fields)
      : null;
    return raw ? parseUserProfile(raw) : null;
  }

  /**
   * 按 user_id 幂等 upsert（先查后更 / 无则建）
   */
  async upsertUserProfile(input: UpsertUserProfileInput): Promise<MemoryBitableUpsertResult> {
    this.assertConfigured();
    const now = Date.now();
    const ref = this.profileRef();
    const existing = await this.getUserProfileByUserId(input.user_id);
    const merged = this.mergeUserProfile(existing, input, now);
    const fields = encodeMemoryFields(MEMORY_USER_PROFILE_FIELD_MAP, merged as unknown as Record<string, unknown>, {
      joinArrayValues: true,
    });

    return this.withTransientRetry('memory.upsertUserProfile', async () =>
      this.bitable.upsertRecordInTable(ref, {
        lockKey: `memory:user_profile:${input.user_id}`,
        filter: buildTextEqFilter(MEMORY_USER_PROFILE_FIELD_MAP.user_id, input.user_id),
        fields,
        fieldSchema: MEMORY_USER_PROFILE_SCHEMA,
      }),
    );
  }

  /**
   * 仅新增一条岗位过程记忆（若需按 job_record_id 去重，请在上层先查再决定 update）
   */
  async createJobRecord(record: JobRecordMemory): Promise<{ recordId: string }> {
    this.assertConfigured();
    const ref = this.jobRef();
    const fields = encodeMemoryFields(MEMORY_JOB_RECORDS_FIELD_MAP, record as unknown as Record<string, unknown>, {
      joinArrayValues: true,
    });
    return this.withTransientRetry('memory.createJobRecord', () =>
      this.bitable.createRecordInTable(ref, fields, MEMORY_JOB_RECORDS_SCHEMA),
    );
  }

  /**
   * 按用户拉取最近岗位记录（按「处理时间」倒序）
   */
  async findRecentJobRecordsByUserId(
    userId: string,
    options?: FindRecentJobRecordsOptions,
  ): Promise<JobRecordMemory[]> {
    if (!userId.trim() || !this.isConfigured()) return [];
    const limit = options?.limit ?? MEMORY_RECENT_JOB_RECORDS_LIMIT;
    const ref = this.jobRef();
    const res = await this.withTransientRetry('memory.findRecentJobRecords', () =>
      this.bitable.searchRecordsInTable(
        ref,
        {
          page_size: limit,
          sort: [{ field_name: MEMORY_JOB_RECORDS_FIELD_MAP.job_date, desc: true }],
          filter: buildTextEqFilter(MEMORY_JOB_RECORDS_FIELD_MAP.user_id, userId),
        },
        MEMORY_JOB_RECORDS_SCHEMA,
      ),
    );
    return res.items
      .map((it) => rowKeysToObject(MEMORY_JOB_RECORDS_FIELD_MAP, it.fields))
      .map(parseJobRecord)
      .filter((r): r is JobRecordMemory => r !== null);
  }

  /**
   * 在最近池中按「技能标签交叠数」粗排，交叠为 0 时按时间补足（不做向量检索）
   */
  async findSimilarJobRecordsByUserId(params: FindSimilarJobRecordsParams): Promise<JobRecordMemory[]> {
    const { userId, skillTags } = params;
    const limit = params.limit ?? MEMORY_CONTEXT_SIMILAR_JOBS_N;
    const poolSize = params.recentPoolSize ?? MEMORY_RECENT_JOB_RECORDS_LIMIT;
    const pool = await this.findRecentJobRecordsByUserId(userId, { limit: poolSize });
    return FeishuMemoryBitableService.rankSimilarJobs(pool, skillTags, limit);
  }

  /**
   * 读取周期总结；未指定 periodKey 时默认按 rolling_30d → all_time → rolling_90d 回退
   */
  async getMemorySummaryByUserId(
    userId: string,
    options?: GetMemorySummaryOptions,
  ): Promise<MemorySummaryRecord | null> {
    if (!userId.trim() || !this.isConfigured()) return null;
    const ref = this.summaryRef();
    const fallback = options?.fallback !== false;

    const fetchOne = async (periodKey: MemoryPeriodKey): Promise<MemorySummaryRecord | null> => {
      const res = await this.withTransientRetry(`memory.getMemorySummary.${periodKey}`, () =>
        this.bitable.searchRecordsInTable(
          ref,
          {
            page_size: 1,
            filter: buildUserAndPeriodFilter(
              MEMORY_SUMMARY_FIELD_MAP.user_id,
              userId,
              MEMORY_SUMMARY_FIELD_MAP.period_key,
              periodKey,
            ),
          },
          MEMORY_SUMMARY_SCHEMA,
        ),
      );
      const raw = res.items[0]?.fields
        ? rowKeysToObject(MEMORY_SUMMARY_FIELD_MAP, res.items[0].fields)
        : null;
      return raw ? parseMemorySummary(raw) : null;
    };

    if (options?.periodKey) {
      return fetchOne(options.periodKey);
    }
    if (!fallback) return null;

    return (
      (await fetchOne(MemoryPeriodKey.ROLLING_30D)) ??
      (await fetchOne(MemoryPeriodKey.ALL_TIME)) ??
      (await fetchOne(MemoryPeriodKey.ROLLING_90D))
    );
  }

  /**
   * 按 summary_id 幂等 upsert（先查后更 / 无则建；存在则与已有行浅合并后再写入）
   */
  async upsertMemorySummary(row: MemorySummaryRecord): Promise<MemoryBitableUpsertResult> {
    this.assertConfigured();
    const ref = this.summaryRef();
    const now = Date.now();
    const withTime: MemorySummaryRecord = { ...row, updated_at: row.updated_at ?? now };

    return this.withTransientRetry('memory.upsertMemorySummary', async () => {
      const search = await this.bitable.searchRecordsInTable(
        ref,
        {
          page_size: 1,
          filter: buildTextEqFilter(MEMORY_SUMMARY_FIELD_MAP.summary_id, withTime.summary_id),
        },
        MEMORY_SUMMARY_SCHEMA,
      );
      const hit = search.items[0];
      const existingRaw = hit?.fields ? rowKeysToObject(MEMORY_SUMMARY_FIELD_MAP, hit.fields) : null;
      const existing = existingRaw ? parseMemorySummary(existingRaw) : null;
      const merged = this.mergeMemorySummary(existing, withTime);
      const fields = encodeMemoryFields(MEMORY_SUMMARY_FIELD_MAP, merged as unknown as Record<string, unknown>, {
        joinArrayValues: true,
      });
      return this.bitable.upsertRecordInTable(ref, {
        lockKey: `memory:summary:${withTime.summary_id}`,
        filter: buildTextEqFilter(MEMORY_SUMMARY_FIELD_MAP.summary_id, withTime.summary_id),
        fields,
        fieldSchema: MEMORY_SUMMARY_SCHEMA,
      });
    });
  }
}

export const feishuMemoryBitableService = new FeishuMemoryBitableService(feishuBitableService);
