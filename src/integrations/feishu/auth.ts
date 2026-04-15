import axios from 'axios';
import { config } from '../../config';
import { createLogger } from '../../utils/logger';
import { FEISHU_API_BASE } from '../../constants';
import type { FeishuTokenResponse } from '../../types';

const log = createLogger('FeishuAuth');

/**
 * 飞书 Tenant Access Token 管理
 * 使用自建应用的 app_id + app_secret 获取 tenant_access_token
 */
class FeishuTokenManager {
  private token: string = '';
  private expiresAt: number = 0;

  /**
   * 获取有效的 tenant_access_token（自动续期）
   */
  async getToken(): Promise<string> {
    // 提前 5 分钟刷新
    if (this.token && Date.now() < this.expiresAt - 5 * 60 * 1000) {
      return this.token;
    }

    log.info('正在获取飞书 tenant_access_token...');

    try {
      const resp = await axios.post<FeishuTokenResponse>(
        `${FEISHU_API_BASE}/auth/v3/tenant_access_token/internal`,
        {
          app_id: config.feishu.appId,
          app_secret: config.feishu.appSecret,
        },
        {
          headers: { 'Content-Type': 'application/json' },
          timeout: 10000,
        },
      );

      if (resp.data.code !== 0 || !resp.data.tenant_access_token) {
        throw new Error(`获取 token 失败: code=${resp.data.code}, msg=${resp.data.msg}`);
      }

      this.token = resp.data.tenant_access_token;
      // expire 单位是秒
      this.expiresAt = Date.now() + (resp.data.expire || 7200) * 1000;

      log.info('tenant_access_token 获取成功', {
        expire: resp.data.expire,
      });

      return this.token;
    } catch (err) {
      log.error('获取 tenant_access_token 失败', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 获取带 Authorization 头的通用请求头
   */
  async getAuthHeaders(): Promise<Record<string, string>> {
    const token = await this.getToken();
    return {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    };
  }
}

/** 单例 */
export const feishuAuth = new FeishuTokenManager();
