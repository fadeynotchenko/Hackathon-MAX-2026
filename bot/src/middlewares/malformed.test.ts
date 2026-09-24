import { describe, expect, it, vi } from 'vitest';

import { silentLogger } from '../logger.js';
import { UNREADABLE_TEXT, malformedUpdateGuard } from './malformed.js';

function run(update: Record<string, unknown>, updateType = 'message_created') {
  const log = silentLogger();
  const warn = vi.spyOn(log, 'warn');
  const sendMessageToChat = vi.fn().mockResolvedValue(undefined);
  const next = vi.fn().mockResolvedValue(undefined);
  const ctx = { update, updateType, api: { sendMessageToChat } };
  return { log, warn, sendMessageToChat, next, done: malformedUpdateGuard(log)(ctx as never, next) };
}

describe('malformed update guard', () => {
  it('passes a normal message on', async () => {
    const { next, warn, done } = run({ message: { sender: { user_id: 1 } } });
    await done;
    expect(next).toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
  });

  it('passes other update types on', async () => {
    const { next, done } = run({ callback: {} }, 'message_callback');
    await done;
    expect(next).toHaveBeenCalled();
  });

  it('stops a message_created without message, logs its shape and asks to resend', async () => {
    const { next, warn, sendMessageToChat, done } = run({
      update_type: 'message_created',
      chat_id: 42,
      user_id: 7,
      voice: { url: 'https://secret', duration: 15 },
    });
    await done;
    expect(next).not.toHaveBeenCalled();
    expect(sendMessageToChat).toHaveBeenCalledWith(42, UNREADABLE_TEXT);
    const [fields] = warn.mock.calls[0]!;
    expect(fields).toMatchObject({
      event: 'bot.update.malformed',
      chat_id: 42,
      user_id: 7,
      shape: { voice: '{duration,url}', chat_id: 'number' },
    });
    expect(JSON.stringify(fields)).not.toContain('secret');
  });
});
