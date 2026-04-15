import axios from 'axios';
import dayjs from 'dayjs';
import { feishuAuth } from './auth';
import { createLogger } from '../../utils/logger';
import { FEISHU_API_BASE, TASK_DUE_DAYS } from '../../constants';
import type { FeishuTaskResponse } from '../../types';

const log = createLogger('FeishuTask');

export interface CreateTaskParams {
  title: string;
  description?: string;
  dueTimestamp?: number; // Unix 秒级时间戳
}

/**
 * 飞书任务服务
 *
 * 使用飞书任务 API v2 创建任务
 * 文档：https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/task-v2/task/create
 */
export class FeishuTaskService {
  /**
   * 创建一个任务
   */
  async createTask(params: CreateTaskParams): Promise<{ taskId: string }> {
    log.info('创建飞书任务', { title: params.title });

    const dueTs = params.dueTimestamp || dayjs().add(TASK_DUE_DAYS, 'day').unix();

    try {
      const headers = await feishuAuth.getAuthHeaders();
      const url = `${FEISHU_API_BASE}/task/v2/tasks`;

      const body = {
        summary: params.title,
        description: params.description || '',
        due: {
          timestamp: String(dueTs),
          is_all_day: false,
        },
        // TODO: 如需将任务分配给特定用户，可增加 members 字段
        // members: [{ id: "ou_xxxxx", type: "user", role: "assignee" }],
      };

      const resp = await axios.post<FeishuTaskResponse>(url, body, {
        headers,
        timeout: 15000,
      });

      if (resp.data.code !== 0) {
        throw new Error(`任务创建失败: code=${resp.data.code}, msg=${resp.data.msg}`);
      }

      const taskId = resp.data.data?.task?.guid || 'unknown';
      log.info(`飞书任务创建成功: taskId=${taskId}`);

      return { taskId };
    } catch (err) {
      log.error('飞书任务创建异常', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 创建投递跟进任务（业务快捷方法）
   */
  async createFollowUpTask(
    companyName: string,
    jobTitle: string,
    summary: string,
  ): Promise<{ taskId: string }> {
    const title = `跟进投递：${companyName} - ${jobTitle}`;
    const description = [
      `📋 岗位摘要：`,
      summary,
      ``,
      `✅ 建议行动：`,
      `1. 根据简历建议优化简历`,
      `2. 准备面试题回答`,
      `3. 投递岗位并记录状态`,
      `4. 一周内无反馈则主动跟进`,
    ].join('\n');

    return this.createTask({ title, description });
  }
}

export const feishuTaskService = new FeishuTaskService();
