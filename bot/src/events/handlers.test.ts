import { describe, expect, it, vi } from 'vitest';

import { silentLogger } from '../logger.js';
import { NOTIFY_USER } from './codec.js';
import { HandlerRejected } from './consumer.js';
import { coreEventHandlers } from './handlers.js';

function setup(sendImpl: () => Promise<unknown>, markerSet = 'OK') {
  const sendMessageToUser = vi.fn().mockImplementation(sendImpl);
  const redis = { set: vi.fn().mockResolvedValue(markerSet), del: vi.fn().mockResolvedValue(1) };
  const handlers = coreEventHandlers(
    { api: { sendMessageToUser } } as never,
    redis as never,
    silentLogger(),
  );
  const event = {
    id: 'evt-1',
    v: 1,
    type: NOTIFY_USER,
    payload: { max_user_id: 5, text: 'hi', format: null },
    ts: '',
    source: 'api',
    streamId: '1-0',
  };
  return { sendMessageToUser, redis, handler: handlers[NOTIFY_USER]!, event };
}

describe('notify.user handler', () => {
  it('sends once and records the event id', async () => {
    const { handler, event, sendMessageToUser, redis } = setup(() => Promise.resolve({}));
    await handler(event);
    expect(sendMessageToUser).toHaveBeenCalledWith(5, 'hi', {});
    expect(redis.set).toHaveBeenCalledWith(
      'events:delivered:evt-1',
      '1',
      'EX',
      expect.any(Number),
      'NX',
    );
  });

  it('skips a redelivered event without sending', async () => {
    const { handler, event, sendMessageToUser } = setup(() => Promise.resolve({}), null as never);
    await handler(event);
    expect(sendMessageToUser).not.toHaveBeenCalled();
  });

  it('clears the marker and rejects permanently on 403', async () => {
    const { handler, event, redis } = setup(() =>
      Promise.reject(Object.assign(new Error('blocked'), { status: 403 })),
    );
    await expect(handler(event)).rejects.toBeInstanceOf(HandlerRejected);
    expect(redis.del).toHaveBeenCalledWith('events:delivered:evt-1');
  });

  it('clears the marker and rethrows transient errors', async () => {
    const { handler, event, redis } = setup(() => Promise.reject(new Error('timeout')));
    await expect(handler(event)).rejects.toThrow('timeout');
    expect(redis.del).toHaveBeenCalledTimes(1);
  });
});
