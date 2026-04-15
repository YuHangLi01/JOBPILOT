import { config } from '../config';
import {
  MEMORY_RECENT_JOB_RECORDS_LIMIT,
  MEMORY_SUMMARY_FIELD_MAP,
  MEMORY_SUMMARY_SCHEMA,
} from '../constants';
import { feishuBitableService, feishuMemoryBitableService } from '../integrations/feishu/bitable';
import {
  buildTextEqFilter,
  encodeMemoryFields,
  parseMemorySummary,
  rowKeysToObject,
} from '../integrations/feishu/bitable-memory.codec';
import { createLogger } from '../utils/logger';
import type {
  BitableTableRef,
  GetMemorySummaryOptions,
  JobRecordMemory,
  MemorySummaryRecord,
  ServiceResult,
  UpdateDerivedMemoryInput,
} from '../types';
import { MemoryPeriodKey } from '../types';

const log = createLogger('DerivedMemory');

const ROLLING_MS = 30 * 24 * 60 * 60 * 1000;
/** 规则版 summary 结构版本，与 LLM 版区分时可 bump */
const SUMMARY_VERSION_RULES = 1;

function makeSummaryId(userId: string, period: MemoryPeriodKey): string {
  return `${userId}__${period}`;
}

/**
 * 派生记忆：memory_summary 表
 *
 * 职责：读取 / 写入周期总结；从 job_records 归纳 rolling 摘要。
 *
 * **memory_summary 生成取舍（比赛 demo）**
 * - 默认 `buildRolling30dSummaryRuleBased`：按 gap/matched 标签频次、最近建议摘要拼接，**零额外 LLM 成本、稳定可展示**；缺点是语义较粗、无法做深层归因。
 * - 可选后续：增加 `refreshRolling30dWithLlm(...)`，把「近期 job_records + 画像」压缩为短摘要写入同表；**表达更自然**，但增加延迟、费用与失败面，需与规则版一样做 try/catch 降级。
 */
export class DerivedMemoryService {
  private isMemoryFullyConfigured(): boolean {
    const f = config.feishu;
    return Boolean(f.memoryUserProfileTableId && f.memoryJobRecordsTableId && f.memorySummaryTableId);
  }

  private summaryRef(): BitableTableRef {
    return {
      appToken: config.feishu.memoryBitableAppToken,
      tableId: config.feishu.memorySummaryTableId,
    };
  }

  /**
   * 读取总结（带周期与回退策略，委托集成层）
   */
  async getByUserId(userId: string, options?: GetMemorySummaryOptions): Promise<MemorySummaryRecord | null> {
    if (!userId.trim() || !this.isMemoryFullyConfigured()) return null;
    try {
      return await feishuMemoryBitableService.getMemorySummaryByUserId(userId, options);
    } catch (err) {
      log.warn('读取 memory_summary 失败（已降级）', err instanceof Error ? err.message : err);
      return null;
    }
  }

  /**
   * 写入完整 summary 行（幂等 upsert）
   */
  async upsertFullRow(row: MemorySummaryRecord): Promise<ServiceResult> {
    if (!this.isMemoryFullyConfigured()) {
      return { success: false, error: 'memory_tables_not_configured' };
    }
    try {
      const { recordId } = await feishuMemoryBitableService.upsertMemorySummary(row);
      return { success: true, recordId };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.warn('写入 memory_summary 失败', msg);
      return { success: false, error: msg };
    }
  }

  /**
   * 部分字段更新：先按 summary_id 查飞书记录再浅合并（供编排层 patch）
   */
  async patchSummary(
    patch: NonNullable<UpdateDerivedMemoryInput['memory_summary_upsert']>,
  ): Promise<ServiceResult> {
    if (!this.isMemoryFullyConfigured()) {
      return { success: false, error: 'memory_tables_not_configured' };
    }
    const ref = this.summaryRef();
    const now = Date.now();
    try {
      const res = await feishuBitableService.searchRecordsInTable(
        ref,
        {
          page_size: 1,
          filter: buildTextEqFilter(MEMORY_SUMMARY_FIELD_MAP.summary_id, patch.summary_id),
        },
        MEMORY_SUMMARY_SCHEMA,
      );
      const hit = res.items[0];
      const existingRaw = hit?.fields ? rowKeysToObject(MEMORY_SUMMARY_FIELD_MAP, hit.fields) : null;
      const existing = existingRaw ? parseMemorySummary(existingRaw) : null;

      const merged: MemorySummaryRecord = existing
        ? { ...existing, ...patch, updated_at: now }
        : {
            summary_id: patch.summary_id,
            user_id: patch.user_id,
            period_key: patch.period_key,
            computed_at: patch.computed_at ?? now,
            source_record_count: patch.source_record_count ?? 0,
            summary_version: patch.summary_version ?? SUMMARY_VERSION_RULES,
            updated_at: now,
            top_target_role_tags: patch.top_target_role_tags,
            top_skill_gap_tags: patch.top_skill_gap_tags,
            top_strength_tags: patch.top_strength_tags,
            weak_points_summary: patch.weak_points_summary,
            recent_similar_job_advice: patch.recent_similar_job_advice,
            action_plan_summary: patch.action_plan_summary,
            evidence_job_ids_json: patch.evidence_job_ids_json,
          };

      const fields = encodeMemoryFields(MEMORY_SUMMARY_FIELD_MAP, merged as unknown as Record<string, unknown>, {
        joinArrayValues: true,
      });
      if (hit) {
        await feishuBitableService.updateRecordInTable(ref, hit.record_id, fields, MEMORY_SUMMARY_SCHEMA);
        return { success: true, recordId: hit.record_id };
      }
      const { recordId } = await feishuBitableService.createRecordInTable(ref, fields, MEMORY_SUMMARY_SCHEMA);
      return { success: true, recordId };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return { success: false, error: msg };
    }
  }

  private static countTopTags(
    rows: JobRecordMemory[],
    key: 'gap_skill_tags' | 'matched_skill_tags',
    topN: number,
  ): string[] {
    const freq = new Map<string, number>();
    for (const j of rows) {
      for (const t of j[key] ?? []) {
        const k = t.trim();
        if (!k) continue;
        freq.set(k, (freq.get(k) ?? 0) + 1);
      }
    }
    return [...freq.entries()].sort((a, b) => b[1] - a[1]).slice(0, topN).map(([t]) => t);
  }

  /**
   * 纯函数：从近期岗位记录归纳 rolling_30d 行（不写表）
   */
  buildRolling30dSummaryRuleBased(userId: string, recentJobs: JobRecordMemory[]): MemorySummaryRecord {
    const now = Date.now();
    const pool = recentJobs.filter((j) => j.job_date >= now - ROLLING_MS);
    const usePool = pool.length > 0 ? pool : recentJobs.slice(0, MEMORY_RECENT_JOB_RECORDS_LIMIT);

    const topGap = DerivedMemoryService.countTopTags(usePool, 'gap_skill_tags', 8);
    const topStrength = DerivedMemoryService.countTopTags(usePool, 'matched_skill_tags', 8);

    const titleFreq = new Map<string, number>();
    for (const j of usePool) {
      const t = j.job_title.trim();
      if (t) titleFreq.set(t, (titleFreq.get(t) ?? 0) + 1);
    }
    const topTitles = [...titleFreq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([t]) => t);

    const adviceSnippets = usePool
      .map((j) => j.resume_advice_summary)
      .filter((s): s is string => Boolean(s && s.trim()))
      .slice(0, 2);
    const recent_similar_job_advice =
      adviceSnippets.length > 0
        ? `最近建议：${adviceSnippets.map((s, i) => `(${i + 1}) ${s.slice(0, 160)}`).join(' / ')}`
        : undefined;

    const weak_points_summary =
      topGap.length > 0
        ? `近期高频技能缺口：${topGap.slice(0, 5).join('、')}。`
        : '近期暂无结构化技能缺口记录。';

    const action_plan_summary =
      topGap.length > 0
        ? `1) 补强「${topGap[0]}」；2) 面试准备与「${topGap.slice(0, 2).join('、')}」相关的项目话术。`
        : '保持投递节奏，补充可量化成果描述。';

    return {
      summary_id: makeSummaryId(userId, MemoryPeriodKey.ROLLING_30D),
      user_id: userId,
      period_key: MemoryPeriodKey.ROLLING_30D,
      computed_at: now,
      source_record_count: usePool.length,
      top_target_role_tags: topTitles.length ? topTitles : undefined,
      top_skill_gap_tags: topGap.length ? topGap : undefined,
      top_strength_tags: topStrength.length ? topStrength : undefined,
      weak_points_summary,
      recent_similar_job_advice,
      action_plan_summary,
      evidence_job_ids_json: JSON.stringify(usePool.slice(0, 5).map((j) => j.job_record_id)),
      summary_version: SUMMARY_VERSION_RULES,
      updated_at: now,
    };
  }

  /**
   * 用规则重算 rolling_30d 并写入多维表格（失败返回 ServiceResult，不抛错）
   */
  async refreshRolling30dFromJobs(userId: string, recentJobs: JobRecordMemory[]): Promise<ServiceResult> {
    if (!userId.trim()) {
      return { success: false, error: 'empty_user_id' };
    }
    if (!this.isMemoryFullyConfigured()) {
      return { success: false, error: 'memory_tables_not_configured' };
    }
    try {
      const row = this.buildRolling30dSummaryRuleBased(userId, recentJobs);
      return await this.upsertFullRow(row);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return { success: false, error: msg };
    }
  }
}

export const derivedMemoryService = new DerivedMemoryService();
