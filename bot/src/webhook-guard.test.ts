import { describe, expect, it, vi } from 'vitest';

import { webhooksInTheWay } from './webhook-guard.js';

const subscription = (url: string) => ({ url, time: 0, updateTypes: [] });

describe('webhooksInTheWay', () => {
  it('reports live subscriptions that polling would remove', async () => {
    const api = {
      getSubscriptions: vi.fn().mockResolvedValue([subscription('https://prod.tld/bot/webhook')]),
    };
    await expect(webhooksInTheWay(api, false)).resolves.toEqual(['https://prod.tld/bot/webhook']);
  });

  it('lets polling start when nothing is subscribed', async () => {
    const api = { getSubscriptions: vi.fn().mockResolvedValue(undefined) };
    await expect(webhooksInTheWay(api, false)).resolves.toEqual([]);
  });

  it('skips the check when taking updates over is allowed', async () => {
    const api = { getSubscriptions: vi.fn() };
    await expect(webhooksInTheWay(api, true)).resolves.toEqual([]);
    expect(api.getSubscriptions).not.toHaveBeenCalled();
  });
});
