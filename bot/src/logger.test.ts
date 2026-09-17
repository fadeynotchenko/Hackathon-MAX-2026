import { mkdtempSync, readFileSync, readdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { createLogger } from './logger.js';

describe('createLogger', () => {
  it('writes json lines with the shared schema to the file stream', async () => {
    const dir = mkdtempSync(join(tmpdir(), 'maxapp-log-'));
    const log = await createLogger({ LOG_LEVEL: 'info', LOG_FORMAT: 'json', LOG_DIR: dir });
    log.warn({ event: 'bot.test', user_id: 7 }, 'hello');
    log.debug({ event: 'bot.hidden' }, 'below level');
    log.flush();
    await new Promise((resolve) => setTimeout(resolve, 100));

    const files = readdirSync(dir).filter((f) => f.startsWith('bot.') && f.endsWith('.log'));
    expect(files.length).toBe(1);
    const lines = readFileSync(join(dir, files[0]!), 'utf8').trim().split('\n');
    expect(lines).toHaveLength(1);
    const record = JSON.parse(lines[0]!) as Record<string, unknown>;
    expect(record['level']).toBe('warning');
    expect(record['service']).toBe('bot');
    expect(record['event']).toBe('bot.test');
    expect(record['msg']).toBe('hello');
    expect(record['user_id']).toBe(7);
    expect(typeof record['ts']).toBe('string');
  });
});
