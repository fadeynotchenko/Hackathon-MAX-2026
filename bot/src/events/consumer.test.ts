import { describe, expect, it, vi } from 'vitest';

import { encodeEvent, NOTIFY_USER } from './codec.js';
import { EventConsumer, HandlerRejected } from './consumer.js';
import { silentLogger } from '../logger.js';

// Минимальная заглушка Redis: одна доставка через XREADGROUP, затем пусто.
function fakeRedis(entries: Array<[string, string[]]>, pendingTimes = 1) {
  let delivered = false;
  const acked: string[] = [];
  const redis = {
    xgroup: vi.fn().mockResolvedValue('OK'),
    xautoclaim: vi.fn().mockResolvedValue(['0-0', [], []]),
    xreadgroup: vi.fn().mockImplementation(async () => {
      if (delivered) return null;
      delivered = true;
      return [['stream', entries]];
    }),
    xpending: vi.fn().mockResolvedValue(entries.map(([id]) => [id, 'c', 0, pendingTimes])),
    xack: vi.fn().mockImplementation(async (_s: string, _g: string, id: string) => {
      acked.push(id);
      return 1;
    }),
  };
  return { redis, acked };
}

function flat(fields: Record<string, string>): string[] {
  return Object.entries(fields).flat();
}

async function runOnce(redis: unknown, handlers: Record<string, (e: never) => Promise<void>>) {
  const consumer = new EventConsumer(redis as never, silentLogger(), {
    stream: 'stream',
    group: 'bot',
    consumer: 'test',
    handlers: handlers as never,
    blockMs: 1,
  });
  await consumer.start();
  await new Promise((resolve) => setTimeout(resolve, 20));
  await consumer.stop();
}

describe('EventConsumer', () => {
  it('handles and acks a valid event', async () => {
    const { fields } = encodeEvent(
      NOTIFY_USER,
      { max_user_id: 1, text: 'x', format: null },
      'api',
      new Date(),
    );
    const { redis, acked } = fakeRedis([['1-0', flat(fields)]]);
    const handler = vi.fn().mockResolvedValue(undefined);
    await runOnce(redis, { [NOTIFY_USER]: handler });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(acked).toEqual(['1-0']);
  });

  it('acks events without a handler and broken envelopes', async () => {
    const { fields } = encodeEvent(
      NOTIFY_USER,
      { max_user_id: 1, text: 'x', format: null },
      'api',
      new Date(),
    );
    const { redis, acked } = fakeRedis([
      ['1-0', flat({ ...fields, type: 'other.type' })],
      ['2-0', flat({ payload: '{}' })],
    ]);
    await runOnce(redis, {});
    expect(acked.sort()).toEqual(['1-0', '2-0']);
  });

  it('acks rejected events but keeps transient failures pending', async () => {
    const { fields } = encodeEvent(
      NOTIFY_USER,
      { max_user_id: 1, text: 'x', format: null },
      'api',
      new Date(),
    );
    const { redis, acked } = fakeRedis([
      ['1-0', flat(fields)],
      ['2-0', flat({ ...fields, id: 'second' })],
    ]);
    await runOnce(redis, {
      [NOTIFY_USER]: async (event: { id: string }) => {
        if (event.id === 'second') throw new Error('temporary');
        throw new HandlerRejected('blocked', 'max_api.403');
      },
    });
    expect(acked).toEqual(['1-0']);
  });
});
