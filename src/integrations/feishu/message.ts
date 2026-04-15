import axios from 'axios';
import { feishuAuth } from './auth';
import { createLogger } from '../../utils/logger';
import { FEISHU_API_BASE } from '../../constants';

const log = createLogger('FeishuMessage');

/**
 * 飞书消息发送服务
 */
export class FeishuMessageService {
  /**
   * 回复消息（通过 message_id 回复）
   */
  async replyText(messageId: string, text: string): Promise<void> {
    try {
      const headers = await feishuAuth.getAuthHeaders();
      await axios.post(
        `${FEISHU_API_BASE}/im/v1/messages/${messageId}/reply`,
        {
          content: JSON.stringify({ text }),
          msg_type: 'text',
        },
        { headers, timeout: 10000 },
      );
      log.info(`文本消息回复成功: messageId=${messageId}`);
    } catch (err) {
      log.error('回复文本消息失败', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 回复富文本消息（post 格式）
   */
  async replyPost(messageId: string, title: string, contentParagraphs: PostParagraph[][]): Promise<void> {
    try {
      const headers = await feishuAuth.getAuthHeaders();
      const postContent = {
        zh_cn: {
          title,
          content: contentParagraphs,
        },
      };
      await axios.post(
        `${FEISHU_API_BASE}/im/v1/messages/${messageId}/reply`,
        {
          content: JSON.stringify(postContent),
          msg_type: 'post',
        },
        { headers, timeout: 10000 },
      );
      log.info(`富文本消息回复成功: messageId=${messageId}`);
    } catch (err) {
      log.error('回复富文本消息失败', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 发送卡片消息（交互卡片）
   */
  async replyInteractiveCard(messageId: string, card: FeishuCard): Promise<void> {
    try {
      const headers = await feishuAuth.getAuthHeaders();
      await axios.post(
        `${FEISHU_API_BASE}/im/v1/messages/${messageId}/reply`,
        {
          content: JSON.stringify(card),
          msg_type: 'interactive',
        },
        { headers, timeout: 10000 },
      );
      log.info(`卡片消息回复成功: messageId=${messageId}`);
    } catch (err) {
      log.error('回复卡片消息失败', err instanceof Error ? err.message : err);
      throw err;
    }
  }

  /**
   * 向聊天会话发送文本消息
   */
  async sendTextToChat(chatId: string, text: string): Promise<void> {
    try {
      const headers = await feishuAuth.getAuthHeaders();
      await axios.post(
        `${FEISHU_API_BASE}/im/v1/messages`,
        {
          receive_id: chatId,
          content: JSON.stringify({ text }),
          msg_type: 'text',
        },
        {
          headers,
          timeout: 10000,
          params: { receive_id_type: 'chat_id' },
        },
      );
      log.info(`文本消息发送成功: chatId=${chatId}`);
    } catch (err) {
      log.error('发送文本消息失败', err instanceof Error ? err.message : err);
      throw err;
    }
  }
}

// ===== 飞书消息类型定义 =====

interface PostTextTag {
  tag: 'text';
  text: string;
}
interface PostATag {
  tag: 'a';
  text: string;
  href: string;
}
interface PostBoldTag {
  tag: 'text';
  text: string;
  style?: string[];
}
type PostParagraph = PostTextTag | PostATag | PostBoldTag;

interface FeishuCard {
  config?: { wide_screen_mode?: boolean };
  header?: {
    title: { tag: string; content: string };
    template?: string;
  };
  elements: FeishuCardElement[];
}

interface FeishuCardElement {
  tag: string;
  text?: { tag: string; content: string };
  content?: string;
  actions?: FeishuCardElement[];
  url?: { val: string };
  type?: string;
}

export const feishuMessageService = new FeishuMessageService();
