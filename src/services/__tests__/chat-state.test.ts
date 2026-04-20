import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { ChatStateService } from '../chat-state.service';

describe('ChatStateService', () => {
  let svc: ChatStateService;

  beforeEach(() => {
    svc = new ChatStateService();
  });

  it('returns undefined for unknown chatId', () => {
    expect(svc.get('unknown')).toBeUndefined();
  });

  it('isInInterview returns false before startInterview', () => {
    expect(svc.isInInterview('chat1')).toBe(false);
  });

  it('startInterview sets status to in_interview', () => {
    svc.startInterview('chat1', 'session-abc');
    const state = svc.get('chat1');
    expect(state).toBeDefined();
    expect(state!.status).toBe('in_interview');
    expect(state!.sessionId).toBe('session-abc');
    expect(svc.isInInterview('chat1')).toBe(true);
  });

  it('endInterview sets status to idle', () => {
    svc.startInterview('chat1', 'session-abc');
    svc.endInterview('chat1');
    expect(svc.isInInterview('chat1')).toBe(false);
    expect(svc.get('chat1')?.status).toBe('idle');
  });

  it('prune removes expired entries', () => {
    // Manually insert a state with expired timestamp
    svc.startInterview('chat-old', 'sess');
    const state = svc.get('chat-old')!;
    // Backdate lastActiveAt by 25 hours
    (state as { lastActiveAt: number }).lastActiveAt = Date.now() - 25 * 60 * 60 * 1000;

    svc.prune();
    expect(svc.get('chat-old')).toBeUndefined();
  });

  it('get returns undefined for expired entries', () => {
    svc.startInterview('chat-expire', 'sess');
    const state = svc.get('chat-expire')!;
    (state as { lastActiveAt: number }).lastActiveAt = Date.now() - 25 * 60 * 60 * 1000;
    expect(svc.get('chat-expire')).toBeUndefined();
  });
});
