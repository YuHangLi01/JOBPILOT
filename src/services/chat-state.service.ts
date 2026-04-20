/**
 * 聊天会话状态管理（内存实现，服务重启后状态丢失）。
 *
 * 每个飞书 chat_id 对应一条 ChatState，TTL 24 小时。
 * thread_id 与 chat_id 相同——用飞书群/单聊 ID 作为 LangGraph 的 thread_id。
 */

const TTL_MS = 24 * 60 * 60 * 1000;

export interface ChatState {
  sessionId: string;
  status: 'idle' | 'in_interview';
  lastActiveAt: number;
}

export class ChatStateService {
  private readonly states = new Map<string, ChatState>();

  get(chatId: string): ChatState | undefined {
    const s = this.states.get(chatId);
    if (!s) return undefined;
    if (Date.now() > s.lastActiveAt + TTL_MS) {
      this.states.delete(chatId);
      return undefined;
    }
    return s;
  }

  isInInterview(chatId: string): boolean {
    return this.get(chatId)?.status === 'in_interview';
  }

  startInterview(chatId: string, sessionId: string): void {
    this.states.set(chatId, {
      sessionId,
      status: 'in_interview',
      lastActiveAt: Date.now(),
    });
  }

  endInterview(chatId: string): void {
    const s = this.states.get(chatId);
    if (s) {
      s.status = 'idle';
      s.lastActiveAt = Date.now();
    }
  }

  touch(chatId: string): void {
    const s = this.states.get(chatId);
    if (s) s.lastActiveAt = Date.now();
  }

  prune(): void {
    const now = Date.now();
    for (const [chatId, s] of this.states) {
      if (now > s.lastActiveAt + TTL_MS) {
        this.states.delete(chatId);
      }
    }
  }
}

export const chatStateService = new ChatStateService();
