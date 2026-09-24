import { describe, expect, it, vi } from 'vitest';

import { silentLogger } from '../logger.js';
import { FAILURE_TEXT, handlerFailure } from './failure.js';

describe('handler failure', () => {
  it('logs the error and tells the user', async () => {
    const log = silentLogger();
    const error = vi.spyOn(log, 'error');
    const reply = vi.fn().mockResolvedValue(undefined);
    await handlerFailure(log)(new Error('boom'), { updateType: 'message_created', chatId: 3, reply } as never);
    expect(error).toHaveBeenCalledWith(
      expect.objectContaining({ event: 'bot.handler.error' }),
      'handler failed',
    );
    expect(reply).toHaveBeenCalledWith(FAILURE_TEXT);
  });

  it('survives a context that breaks on reading the chat', async () => {
    const log = silentLogger();
    const ctx = {
      updateType: 'message_created',
      get chatId(): number {
        throw new TypeError("Cannot read properties of undefined (reading 'recipient')");
      },
    };
    await expect(handlerFailure(log)(new Error('boom'), ctx as never)).resolves.toBeUndefined();
  });
});
