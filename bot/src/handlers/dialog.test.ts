import { describe, expect, it, vi } from 'vitest';

import { EventPublisher } from '../events/publisher.js';
import { silentLogger } from '../logger.js';
import { DOC_ACTION, NON_TEXT_HINT, UNKNOWN_COMMAND_TEXT, registerDialog } from './dialog.js';

type Handler = (ctx: unknown) => Promise<void>;

function setup() {
  const xadd = vi.fn().mockResolvedValue('1-0');
  const publisher = new EventPublisher(
    { xadd } as unknown as ConstructorParameters<typeof EventPublisher>[0],
    silentLogger(),
    { stream: 'to_core', maxlen: 10 },
  );
  const handlers: { on?: Handler; action?: Handler; trigger?: unknown } = {};
  const bot = {
    on: (_type: string, handler: Handler) => {
      handlers.on = handler;
    },
    action: (trigger: unknown, handler: Handler) => {
      handlers.trigger = trigger;
      handlers.action = handler;
    },
  };
  registerDialog(bot as never, { publisher, log: silentLogger() });
  return { xadd, handlers };
}

function published(xadd: ReturnType<typeof vi.fn>) {
  const args = xadd.mock.calls[0] as unknown[];
  const fields = Object.fromEntries(
    Array.from({ length: (args.length - 5) / 2 }, (_, i) => [args[5 + 2 * i], args[6 + 2 * i]]),
  ) as Record<string, string>;
  return { type: fields['type'], payload: JSON.parse(fields['payload']!) as unknown };
}

function textMessage(text: string | undefined, chatType = 'dialog') {
  const reply = vi.fn().mockResolvedValue(undefined);
  return {
    reply,
    ctx: {
      reply,
      message: {
        recipient: { chat_type: chatType, chat_id: 77 },
        body: { text },
        sender: { user_id: 5, first_name: 'Ann', last_name: null, username: 'ann' },
      },
    },
  };
}

describe('dialog', () => {
  it('forwards free text to core as bot.message', async () => {
    const { xadd, handlers } = setup();
    const { ctx, reply } = textMessage('  Счёт на 120 000 для ООО Ромашка ');
    await handlers.on!(ctx);

    expect(reply).not.toHaveBeenCalled();
    expect(published(xadd)).toEqual({
      type: 'bot.message',
      payload: {
        max_user_id: 5,
        chat_id: 77,
        text: 'Счёт на 120 000 для ООО Ромашка',
        first_name: 'Ann',
        last_name: null,
        username: 'ann',
      },
    });
  });

  it('answers non-text and unknown commands itself', async () => {
    const { xadd, handlers } = setup();
    const photo = textMessage(undefined);
    await handlers.on!(photo.ctx);
    const command = textMessage('/deploy');
    await handlers.on!(command.ctx);

    expect(photo.reply).toHaveBeenCalledWith(NON_TEXT_HINT);
    expect(command.reply).toHaveBeenCalledWith(UNKNOWN_COMMAND_TEXT);
    expect(xadd).not.toHaveBeenCalled();
  });

  it('stays silent in group chats', async () => {
    const { xadd, handlers } = setup();
    const { ctx, reply } = textMessage('всем привет', 'chat');
    await handlers.on!(ctx);
    expect(reply).not.toHaveBeenCalled();
    expect(xadd).not.toHaveBeenCalled();
  });

  it('forwards document buttons and strips them from the pressed message', async () => {
    const { xadd, handlers } = setup();
    expect((handlers.trigger as RegExp).source).toBe(DOC_ACTION.source);
    const answerOnCallback = vi.fn().mockResolvedValue({ success: true });
    await handlers.action!({
      callback: { payload: 'doc:confirm:12' },
      user: { user_id: 5 },
      chatId: 77,
      message: { body: { text: 'Счёт на оплату: проверьте значения' } },
      answerOnCallback,
    });

    expect(published(xadd)).toEqual({
      type: 'bot.callback',
      payload: { max_user_id: 5, chat_id: 77, payload: 'doc:confirm:12' },
    });
    expect(answerOnCallback).toHaveBeenCalledWith({
      message: { text: 'Счёт на оплату: проверьте значения', attachments: [] },
    });
  });
});
