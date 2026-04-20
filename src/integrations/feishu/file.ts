import axios from 'axios';
import { feishuAuth } from './auth';
import { FEISHU_API_BASE } from '../../constants';
import { createLogger } from '../../utils/logger';

const log = createLogger('FeishuFile');

export interface DownloadFeishuMessageFileResult {
  filename: string;
  mimeType: string;
  buffer: Buffer;
}

function parseFilenameFromDisposition(contentDisposition: string | undefined): string | undefined {
  if (!contentDisposition) return undefined;
  const utf8Match = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
  if (utf8Match?.[1]) {
    return decodeURIComponent(utf8Match[1]);
  }
  const plainMatch = /filename="?([^";]+)"?/i.exec(contentDisposition);
  return plainMatch?.[1];
}

export class FeishuFileService {
  async downloadMessageFile(messageId: string, fileKey: string): Promise<DownloadFeishuMessageFileResult> {
    const token = await feishuAuth.getToken();
    const url = `${FEISHU_API_BASE}/im/v1/messages/${messageId}/resources/${fileKey}`;
    const response = await axios.get<ArrayBuffer>(url, {
      responseType: 'arraybuffer',
      params: { type: 'file' },
      headers: {
        Authorization: `Bearer ${token}`,
      },
      timeout: 30000,
    });

    const contentType = String(response.headers['content-type'] || 'application/octet-stream');
    const contentDisposition = String(response.headers['content-disposition'] || '');
    const filename = parseFilenameFromDisposition(contentDisposition) || `${fileKey}.bin`;

    log.info('飞书文件下载成功', {
      messageId,
      fileKey,
      filename,
      contentType,
      size: response.data.byteLength,
    });

    return {
      filename,
      mimeType: contentType,
      buffer: Buffer.from(response.data),
    };
  }
}

export const feishuFileService = new FeishuFileService();
