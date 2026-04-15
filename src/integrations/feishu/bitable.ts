import axios from 'axios';
import { feishuAuth } from './auth';
import { config } from '../../config';
import { createLogger } from '../../utils/logger';
import { FEISHU_API_BASE, BITABLE_FIELD_MAP } from '../../constants';
import type { BitableRecord, FeishuBitableResponse } from '../../types';

const log = createLogger('FeishuBitable');

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
 * 配置完成后将 app_token 和 table_id 填入 .env
 */
export class FeishuBitableService {
  private appToken: string;
  private tableId: string;

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

    try {
      const headers = await feishuAuth.getAuthHeaders();
      const url = `${FEISHU_API_BASE}/bitable/v1/apps/${this.appToken}/tables/${this.tableId}/records`;

      // 将字段名映射为中文表头名
      const fields: Record<string, unknown> = {};
      for (const [key, label] of Object.entries(BITABLE_FIELD_MAP)) {
        const value = record[key as keyof BitableRecord];
        if (key === 'created_at') {
          // 多维表格日期字段接受毫秒时间戳
          fields[label] = value;
        } else {
          fields[label] = value;
        }
      }

      const resp = await axios.post<FeishuBitableResponse>(
        url,
        { fields },
        { headers, timeout: 15000 },
      );

      if (resp.data.code !== 0) {
        throw new Error(`多维表格写入失败: code=${resp.data.code}, msg=${resp.data.msg}`);
      }

      const recordId = resp.data.data?.record?.record_id || 'unknown';
      log.info(`多维表格写入成功: recordId=${recordId}`);

      return { recordId };
    } catch (err) {
      log.error('多维表格写入异常', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 批量写入记录（预留扩展）
   */
  async addRecords(records: BitableRecord[]): Promise<void> {
    // TODO: 使用飞书批量新增接口 /bitable/v1/apps/:app_token/tables/:table_id/records/batch_create
    for (const record of records) {
      await this.addRecord(record);
    }
  }
}

export const feishuBitableService = new FeishuBitableService();
