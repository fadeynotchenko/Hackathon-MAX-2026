import { describe, expect, it } from 'vitest';

import { loadConfig } from './config.js';

const base = { MAX_BOT_TOKEN: 'token', REDIS_HOST: 'localhost' };

describe('loadConfig', () => {
  it('applies defaults and treats empty strings as unset', () => {
    const cfg = loadConfig({ ...base, PUBLIC_BASE_URL: '', LOG_LEVEL: 'INFO' });
    expect(cfg.BOT_MODE).toBe('polling');
    expect(cfg.BOT_WEBHOOK_PORT).toBe(8080);
    expect(cfg.PUBLIC_BASE_URL).toBe('');
    expect(cfg.LOG_LEVEL).toBe('info');
  });

  it('maps python-style level names and rejects unknown ones', () => {
    expect(loadConfig({ ...base, LOG_LEVEL: 'WARNING' }).LOG_LEVEL).toBe('warn');
    expect(loadConfig({ ...base, LOG_LEVEL: 'critical' }).LOG_LEVEL).toBe('fatal');
    expect(() => loadConfig({ ...base, LOG_LEVEL: 'loud' })).toThrow(/LOG_LEVEL/);
  });

  it('keeps an explicitly empty LOG_DIR to disable the file log', () => {
    expect(loadConfig({ ...base, LOG_DIR: '' }).LOG_DIR).toBe('');
    expect(loadConfig(base).LOG_DIR).toBe('app_logs');
  });

  it('keeps webhook subscriptions unless polling takeover is explicit', () => {
    expect(loadConfig(base).BOT_POLLING_TAKEOVER).toBe(false);
    expect(loadConfig({ ...base, BOT_POLLING_TAKEOVER: 'true' }).BOT_POLLING_TAKEOVER).toBe(true);
    expect(() => loadConfig({ ...base, BOT_POLLING_TAKEOVER: 'maybe' })).toThrow(
      /BOT_POLLING_TAKEOVER/,
    );
  });

  it('requires the bot token', () => {
    expect(() => loadConfig({ REDIS_HOST: 'x' })).toThrow(/MAX_BOT_TOKEN/);
  });

  it('requires https domain and secret in webhook mode', () => {
    expect(() => loadConfig({ ...base, BOT_MODE: 'webhook' })).toThrow(/PUBLIC_BASE_URL/);
    expect(() =>
      loadConfig({ ...base, BOT_MODE: 'webhook', PUBLIC_BASE_URL: 'https://x.tld' }),
    ).toThrow(/BOT_WEBHOOK_SECRET/);
    const ok = loadConfig({
      ...base,
      BOT_MODE: 'webhook',
      PUBLIC_BASE_URL: 'https://x.tld',
      BOT_WEBHOOK_SECRET: 's'.repeat(16),
    });
    expect(ok.BOT_MODE).toBe('webhook');
  });

  it('refuses dev-only values in production', () => {
    expect(() =>
      loadConfig({ ...base, ENV: 'production', MAX_BOT_TOKEN: 'dev-only-token' }),
    ).toThrow(/dev-плейсхолдер/);
    expect(loadConfig({ ...base, ENV: 'dev', MAX_BOT_TOKEN: 'dev-only-token' }).ENV).toBe('dev');
  });
});
