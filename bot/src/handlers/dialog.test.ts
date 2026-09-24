import { describe, expect, it, vi } from 'vitest';

import { EventPublisher } from '../events/publisher.js';
import { silentLogger } from '../logger.js';
import {
  DOC_ACTION,
  NON_TEXT_HINT,
  UNKNOWN_COMMAND_TEXT,
  pickAttachment,
  registerDialog,
} from './dialog.js';

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

function textMessage(text: string | undefined, chatType = 'dialog', attachments?: unknown[]) {
  const reply = vi.fn().mockResolvedValue(undefined);
  const sendAction = vi.fn().mockResolvedValue({ success: true });
  return {
    reply,
    sendAction,
    ctx: {
      reply,
      sendAction,
      message: {
        recipient: { chat_type: chatType, chat_id: 77 },
        body: { text, attachments },
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

  it('forwards a photo with its caption as bot.attachment', async () => {
    const { xadd, handlers } = setup();
    const { ctx, reply, sendAction } = textMessage(' это покупатель ', 'dialog', [
      { type: 'image', payload: { photo_id: 1, token: 't', url: 'https://i.max.ru/p/1' } },
    ]);
    await handlers.on!(ctx);

    expect(reply).not.toHaveBeenCalled();
    expect(sendAction).toHaveBeenCalledWith('typing_on');
    expect(published(xadd)).toEqual({
      type: 'bot.attachment',
      payload: {
        max_user_id: 5,
        chat_id: 77,
        kind: 'image',
        url: 'https://i.max.ru/p/1',
        filename: null,
        size: null,
        text: 'это покупатель',
        first_name: 'Ann',
        last_name: null,
        username: 'ann',
      },
    });
  });

  it('forwards voice messages and files without a caption', async () => {
    const { xadd, handlers } = setup();
    const voice = textMessage(undefined, 'dialog', [
      { type: 'audio', payload: { url: 'https://a.max.ru/v/1', token: 't' } },
    ]);
    await handlers.on!(voice.ctx);
    expect(published(xadd)).toMatchObject({
      type: 'bot.attachment',
      payload: { kind: 'audio', url: 'https://a.max.ru/v/1', text: null },
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

describe('pickAttachment', () => {
  it('takes the first readable attachment and skips the rest', () => {
    expect(
      pickAttachment([
        { type: 'sticker', payload: { url: 'https://s.max.ru/1', code: 'x' } },
        { type: 'location' },
        {
          type: 'file',
          payload: { url: 'https://f.max.ru/1', token: 't' },
          filename: 'card.pdf',
          size: 1024,
        },
        { type: 'image', payload: { url: 'https://i.max.ru/2', token: 't' } },
      ]),
    ).toEqual({ kind: 'file', url: 'https://f.max.ru/1', filename: 'card.pdf', size: 1024 });
  });

  it('ignores stickers, missing links and plain http', () => {
    expect(pickAttachment(undefined)).toBeNull();
    expect(
      pickAttachment([{ type: 'sticker', payload: { url: 'https://s.max.ru/1' } }]),
    ).toBeNull();
    expect(pickAttachment([{ type: 'image', payload: { token: 't' } }])).toBeNull();
    expect(pickAttachment([{ type: 'image', payload: { url: 'http://i.max.ru/1' } }])).toBeNull();
  });
});
