import { describe, expect, it } from 'vitest';

import { RedisSessionStore, type KeyValueClient } from './redis-store.js';

function fakeClient(): KeyValueClient & { ttl: Map<string, number> } {
  const data = new Map<string, string>();
  const ttl = new Map<string, number>();
  return {
    ttl,
    get: async (key) => data.get(key) ?? null,
    set: async (key, value, _mode, seconds) => {
      data.set(key, value);
      ttl.set(key, seconds);
    },
    del: async (key) => {
      data.delete(key);
      ttl.delete(key);
    },
  };
}

describe('RedisSessionStore', () => {
  it('stores JSON under a prefixed key with TTL', async () => {
    const client = fakeClient();
    const store = new RedisSessionStore<{ starts: number }>(client, { ttlSeconds: 60 });
    await store.set('1:2', { starts: 3 });
    expect(await store.get('1:2')).toEqual({ starts: 3 });
    expect(client.ttl.get('bot:session:1:2')).toBe(60);
    await store.delete('1:2');
    expect(await store.get('1:2')).toBeUndefined();
  });

  it('drops corrupted entries instead of throwing', async () => {
    const client = fakeClient();
    await client.set('bot:session:x', '{not json', 'EX', 1);
    const store = new RedisSessionStore<{ starts: number }>(client, { ttlSeconds: 60 });
    expect(await store.get('x')).toBeUndefined();
    expect(await client.get('bot:session:x')).toBeNull();
  });
});
