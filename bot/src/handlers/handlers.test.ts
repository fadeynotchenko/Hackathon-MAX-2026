import { describe, expect, it, vi } from 'vitest';

import { EventPublisher } from '../events/publisher.js';
import { silentLogger } from '../logger.js';
import { profileText } from './profile.js';
import { WELCOME_TEXT, registerStart } from './start.js';

interface Registered {
  on: Record<string, (ctx: unknown) => Promise<void>>;
  command: Record<string, (ctx: unknown) => Promise<void>>;
}

function fakeBot(): Registered & { bot: unknown } {
  const registered: Registered = { on: {}, command: {} };
  const bot = {
    on: (type: string, handler: (ctx: unknown) => Promise<void>) => {
      registered.on[type] = handler;
    },
    command: (name: string, handler: (ctx: unknown) => Promise<void>) => {
      registered.command[name] = handler;
    },
  };
  return { ...registered, bot };
}

describe('start handler', () => {
  it('greets, bumps the session counter and publishes bot.user_started', async () => {
    const xadd = vi.fn().mockResolvedValue('1-0');
    const publisher = new EventPublisher(
      { xadd } as unknown as ConstructorParameters<typeof EventPublisher>[0],
      silentLogger(),
      { stream: 'to_core', maxlen: 10 },
    );
    const fake = fakeBot();
    registerStart(fake.bot as never, { publisher, log: silentLogger(), keyboard: {} });

    const reply = vi.fn().mockResolvedValue(undefined);
    const ctx = {
      user: { user_id: 5, first_name: 'Ann', last_name: 'Lee', username: 'ann' },
      chatId: 9,
      startPayload: 'ref_1',
      update: { user_locale: 'ru' },
      session: { starts: 1 },
      reply,
    };
    await fake.on['bot_started']!(ctx);

    expect(reply).toHaveBeenCalledWith(
      WELCOME_TEXT,
      expect.objectContaining({ attachments: expect.any(Array) }),
    );
    expect(ctx.session.starts).toBe(2);
    expect(xadd).toHaveBeenCalledTimes(1);
    const args = xadd.mock.calls[0] as unknown[];
    expect(args.slice(0, 5)).toEqual(['to_core', 'MAXLEN', '~', 10, '*']);
    const fields = Object.fromEntries(
      Array.from({ length: (args.length - 5) / 2 }, (_, i) => [args[5 + 2 * i], args[6 + 2 * i]]),
    ) as Record<string, string>;
    expect(fields['type']).toBe('bot.user_started');
    expect(JSON.parse(fields['payload']!)).toMatchObject({
      max_user_id: 5,
      chat_id: 9,
      first_name: 'Ann',
      username: 'ann',
      language_code: 'ru',
      start_payload: 'ref_1',
    });
  });
});

describe('profile text', () => {
  it('renders known user fields', () => {
    const text = profileText({
      user: { user_id: 1, first_name: 'A', last_name: 'B', username: 'ab' },
      session: { starts: 3 },
    } as never);
    expect(text).toContain('Имя: A B');
    expect(text).toContain('ID в MAX: 1');
    expect(text).toContain('@ab');
    expect(text).toContain('Запусков бота: 3');
  });
});
