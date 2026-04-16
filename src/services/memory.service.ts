import { config } from '../config';
import {
  MEMORY_CONTEXT_SIMILAR_JOBS_N,
  MEMORY_JOB_RECORDS_FIELD_MAP,
  MEMORY_JOB_RECORDS_SCHEMA,
  MEMORY_RECENT_JOB_RECORDS_LIMIT,
} from '../constants';
import { feishuBitableService, feishuMemoryBitableService } from '../integrations/feishu/bitable';
import { buildTextEqFilter, encodeMemoryFields } from '../integrations/feishu/bitable-memory.codec';
import { createLogger } from '../utils/logger';
import { derivedMemoryService } from './derived-memory.service';
import { profileMemoryService } from './profile-memory.service';
import type {
  BitableTableRef,
  JobRecordMemory,
  MemoryContextForJobAnalysis,
  RefreshMemoryAfterJobInput,
  RefreshMemoryAfterJobResult,
  SaveJobRecordInput,
  ServiceResult,
  UpdateDerivedMemoryInput,
} from '../types';

const log = createLogger('Memory');

export interface GetMemoryContextOptions {
  /** 当前 JD 解析出的技能标签，用于填充 similar_job_records */
  jdSkillTags?: string[];
}

/**
 * 记忆编排门面：组合 profile / job_records / memory_summary，供简历、面试、投递建议取数。
 *
 * - 过程写入（job_records）仍在本类：需按 job_record_id 幂等 upsert，直接走通用 bitable CRUD。
 * - 稳定画像、派生总结分别委托 profileMemoryService、derivedMemoryService。
 */
export class MemoryService {
  private isMemoryConfigured(): boolean {
    const f = config.feishu;
    return Boolean(f.memoryUserProfileTableId && f.memoryJobRecordsTableId && f.memorySummaryTableId);
  }

  private jobRecordsTableRef(): BitableTableRef {
    return {
      appToken: config.feishu.memoryBitableAppToken,
      tableId: config.feishu.memoryJobRecordsTableId,
    };
  }

  /**
   * 供 JD 分析前拉取：画像 + 最近岗位 + 总结 +（可选）与当前 JD 技能交叠的相似岗位
   */
  async getMemoryContextForJobAnalysis(
    userId: string,
    options?: GetMemoryContextOptions,
  ): Promise<MemoryContextForJobAnalysis> {
    const empty: MemoryContextForJobAnalysis = {
      profile: null,
      recent_job_records: [],
      summary: null,
      similar_job_records: [],
    };
    if (!userId.trim()) return empty;
    if (!this.isMemoryConfigured()) {
      log.debug('记忆表未配置，跳过读取');
      return empty;
    }

    try {
      const [profile, recentFull, summary, similar_job_records] = await Promise.all([
        profileMemoryService.getByUserId(userId),
        feishuMemoryBitableService.findRecentJobRecordsByUserId(userId, {
          limit: MEMORY_RECENT_JOB_RECORDS_LIMIT,
        }),
        derivedMemoryService.getByUserId(userId),
        options?.jdSkillTags?.length
          ? feishuMemoryBitableService.findSimilarJobRecordsByUserId({
              userId,
              skillTags: options.jdSkillTags,
            })
          : Promise.resolve([]),
      ]);

      const recent_job_records = recentFull.slice(0, MEMORY_CONTEXT_SIMILAR_JOBS_N);

      return {
        profile,
        recent_job_records,
        summary,
        similar_job_records,
      };
    } catch (err) {
      log.warn('读取求职记忆失败（已降级）', err instanceof Error ? err.message : err);
      return empty;
    }
  }

  /**
   * 写入 / 更新单条岗位过程记忆（按 job_record_id 幂等去重）
   */
  async saveJobRecord(input: SaveJobRecordInput): Promise<{ success: boolean; recordId?: string; error?: string }> {
    if (!this.isMemoryConfigured()) {
      log.debug('记忆表未配置，跳过写入 job_records');
      return { success: false, error: 'memory_tables_not_configured' };
    }
    const now = Date.now();
    const record: JobRecordMemory = {
      ...input,
      created_at: input.created_at ?? now,
      updated_at: input.updated_at ?? now,
    };
    const ref = this.jobRecordsTableRef();
    const fields = encodeMemoryFields(MEMORY_JOB_RECORDS_FIELD_MAP, record as unknown as Record<string, unknown>, {
      joinArrayValues: true,
    });

    try {
      const { recordId } = await feishuBitableService.upsertRecordInTable(ref, {
        lockKey: `memory:job_record:${record.job_record_id}`,
        filter: buildTextEqFilter(MEMORY_JOB_RECORDS_FIELD_MAP.job_record_id, record.job_record_id),
        fields,
        fieldSchema: MEMORY_JOB_RECORDS_SCHEMA,
      });
      return { success: true, recordId };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.warn('写入 job_records 失败', msg);
      return { success: false, error: msg };
    }
  }

  /**
   * 本次 JD 流水线结束后：落 job_record → 规则刷新 rolling_30d 摘要 → 更新画像活跃时间
   */
  async refreshAfterJobProcessing(input: RefreshMemoryAfterJobInput): Promise<RefreshMemoryAfterJobResult> {
    const jobRecord = await this.saveJobRecord(input.jobRecord);
    let summary: ServiceResult = { success: false, error: 'skipped' };
    if (jobRecord.success) {
      const recent = await feishuMemoryBitableService.findRecentJobRecordsByUserId(input.userId, {
        limit: MEMORY_RECENT_JOB_RECORDS_LIMIT,
      });
      summary = await derivedMemoryService.refreshRolling30dFromJobs(input.userId, recent);
    }
    const profileTouch = await profileMemoryService.touchLastActive(input.userId);
    return { jobRecord, summary, profileTouch };
  }

  /**
   * 更新派生记忆：用户画像 patch、周期总结 patch（委托子服务）
   */
  async updateDerivedMemory(input: UpdateDerivedMemoryInput): Promise<{
    profileOk: boolean;
    summaryOk: boolean;
    errors: string[];
  }> {
    const errors: string[] = [];
    let profileOk = true;
    let summaryOk = true;

    if (!this.isMemoryConfigured()) {
      return { profileOk: false, summaryOk: false, errors: ['memory_tables_not_configured'] };
    }

    if (input.user_profile_upsert) {
      const r = await profileMemoryService.upsert(input.user_profile_upsert);
      profileOk = r.success;
      if (!r.success && r.error) errors.push(r.error);
    }

    if (input.memory_summary_upsert) {
      const r = await derivedMemoryService.patchSummary(input.memory_summary_upsert);
      summaryOk = r.success;
      if (!r.success && r.error) errors.push(r.error);
    }

    return { profileOk, summaryOk, errors };
  }
}

export const memoryService = new MemoryService();
