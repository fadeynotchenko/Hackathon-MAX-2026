import { describe, expect, it, vi } from 'vitest';

import {
  API_TIMEOUT_MS,
  POLLING_TIMEOUT_MS,
  createFetchWithTimeout,
  timeoutFor,
} from './max-fetch.js';

describe('таймауты Bot API', () => {
  it('даёт long polling больше времени, чем обычному вызову', () => {
    expect(timeoutFor('https://platform-api2.max.ru/updates?marker=1')).toBe(POLLING_TIMEOUT_MS);
    expect(timeoutFor('https://platform-api2.max.ru/messages?user_id=1')).toBe(API_TIMEOUT_MS);
    expect(timeoutFor(new URL('https://platform-api2.max.ru/updates'))).toBe(POLLING_TIMEOUT_MS);
  });

  it('передаёт сигнал вызывающего вместе со своим', async () => {
    const base = vi.fn().mockResolvedValue(new Response('{}'));
    const caller = new AbortController();
    await createFetchWithTimeout(base as never)('https://platform-api2.max.ru/me', {
      signal: caller.signal,
    });
    const init = base.mock.calls[0]?.[1] as RequestInit;
    expect(init.signal).toBeInstanceOf(AbortSignal);
    caller.abort();
    expect(init.signal?.aborted).toBe(true);
  });
});
