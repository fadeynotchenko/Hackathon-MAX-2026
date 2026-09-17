import { describe, expect, it, vi } from 'vitest';

import { ApiClient, ApiError } from './client';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ApiClient', () => {
  it('sends bearer token and parses json', async () => {
    const fetchFn = vi.fn().mockResolvedValue(jsonResponse(200, { id: 1 }));
    const client = new ApiClient({ baseUrl: 'http://api', fetchFn });
    client.setAccessToken('tok');
    await expect(client.me()).resolves.toEqual({ id: 1 });
    const [url, init] = fetchFn.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://api/api/v1/me');
    expect((init.headers as Record<string, string>)['Authorization']).toBe('Bearer tok');
    expect(init.credentials).toBe('include');
  });

  it('refreshes once on 401 and retries the original request', async () => {
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'expired', code: 'auth.invalid_token' }))
      .mockResolvedValueOnce(
        jsonResponse(200, { access_token: 'new', token_type: 'bearer', expires_in: 900, user: {} }),
      )
      .mockResolvedValueOnce(jsonResponse(200, { id: 7 }));
    const client = new ApiClient({ baseUrl: '', fetchFn });
    client.setAccessToken('old');
    await expect(client.me()).resolves.toEqual({ id: 7 });
    expect(fetchFn).toHaveBeenCalledTimes(3);
    expect((fetchFn.mock.calls[1] as [string])[0]).toBe('/api/v1/auth/refresh');
    const retryInit = (fetchFn.mock.calls[2] as [string, RequestInit])[1];
    expect((retryInit.headers as Record<string, string>)['Authorization']).toBe('Bearer new');
  });

  it('reports session loss when refresh fails', async () => {
    const onSessionLost = vi.fn();
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'x', code: 'auth.invalid_token' }))
      .mockResolvedValueOnce(
        jsonResponse(401, { detail: 'no session', code: 'auth.refresh.missing' }),
      );
    const client = new ApiClient({ baseUrl: '', fetchFn, onSessionLost });
    client.setAccessToken('old');
    await expect(client.me()).rejects.toMatchObject({ status: 401, code: 'auth.invalid_token' });
    expect(onSessionLost).toHaveBeenCalledTimes(1);
    expect(client.hasToken()).toBe(false);
  });

  it('keeps the token when refresh fails for a transient reason', async () => {
    const onSessionLost = vi.fn();
    const fetchFn = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(401, { detail: 'x', code: 'auth.invalid_token' }))
      .mockResolvedValueOnce(new Response('bad gateway', { status: 502 }));
    const client = new ApiClient({ baseUrl: '', fetchFn, onSessionLost });
    client.setAccessToken('old');
    await expect(client.me()).rejects.toMatchObject({ status: 401 });
    expect(onSessionLost).not.toHaveBeenCalled();
    expect(client.hasToken()).toBe(true);
  });

  it('shares one refresh between parallel 401 responses', async () => {
    let refreshCalls = 0;
    const fetchFn = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return jsonResponse(200, {
          access_token: 'new',
          token_type: 'bearer',
          expires_in: 900,
          user: {},
        });
      }
      const init = fetchFn.mock.calls[fetchFn.mock.calls.length - 1]![1] as RequestInit;
      const auth = (init.headers as Record<string, string>)['Authorization'];
      return auth === 'Bearer new'
        ? jsonResponse(200, { ok: true })
        : jsonResponse(401, { detail: 'x', code: 'auth.invalid_token' });
    });
    const client = new ApiClient({ baseUrl: '', fetchFn });
    client.setAccessToken('old');
    await Promise.all([client.me(), client.adminStats()]);
    expect(refreshCalls).toBe(1);
  });

  it('wraps non-json errors', async () => {
    const fetchFn = vi.fn().mockResolvedValue(new Response('bad gateway', { status: 502 }));
    const client = new ApiClient({ baseUrl: '', fetchFn });
    const error = await client.adminStats().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(502);
    expect((error as ApiError).code).toBe('http.error');
  });
});
