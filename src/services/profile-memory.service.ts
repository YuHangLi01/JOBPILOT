import { config } from '../config';
import { feishuMemoryBitableService } from '../integrations/feishu/bitable';
import { createLogger } from '../utils/logger';
import type { ServiceResult, UpsertUserProfileInput, UserProfileMemory } from '../types';

const log = createLogger('ProfileMemory');

/**
 * 稳定记忆：user_profile 表
 *
 * 职责：读取 / 更新用户求职画像；与 job_records、memory_summary 解耦，便于单独测试与降级。
 */
export class ProfileMemoryService {
  private isMemoryFullyConfigured(): boolean {
    const f = config.feishu;
    return Boolean(f.memoryUserProfileTableId && f.memoryJobRecordsTableId && f.memorySummaryTableId);
  }

  /**
   * 按 userId 读取画像；未配置或失败时返回 null（不抛错）
   */
  async getByUserId(userId: string): Promise<UserProfileMemory | null> {
    if (!userId.trim() || !this.isMemoryFullyConfigured()) return null;
    try {
      return await feishuMemoryBitableService.getUserProfileByUserId(userId);
    } catch (err) {
      log.warn('读取 user_profile 失败（已降级）', err instanceof Error ? err.message : err);
      return null;
    }
  }

  /**
   * 幂等 upsert（依赖集成层按 user_id 去重）
   */
  async upsert(input: UpsertUserProfileInput): Promise<ServiceResult> {
    if (!this.isMemoryFullyConfigured()) {
      return { success: false, error: 'memory_tables_not_configured' };
    }
    try {
      const { recordId } = await feishuMemoryBitableService.upsertUserProfile(input);
      return { success: true, recordId };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      log.warn('写入 user_profile 失败', msg);
      return { success: false, error: msg };
    }
  }

  /**
   * 若已有画像则刷新 last_active_at；无画像不强行建空行（避免 demo 里脏数据）
   */
  async touchLastActive(userId: string): Promise<ServiceResult> {
    if (!userId.trim() || !this.isMemoryFullyConfigured()) {
      return { success: true };
    }
    try {
      const existing = await this.getByUserId(userId);
      if (!existing) return { success: true };
      return this.upsert({ user_id: userId, last_active_at: Date.now() });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return { success: false, error: msg };
    }
  }
}

export const profileMemoryService = new ProfileMemoryService();
