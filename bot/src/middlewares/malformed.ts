// Апдейт message_created без message. Так 2026-09-24 пришло голосовое из клиента
// MAX: SDK падал на чтении sender ещё в middleware сессий, и пользователь не
// получал никакого ответа. Такой апдейт отсекается до сессий; в лог уходит его
// форма (ключи и вложенные ключи, без содержимого), чтобы разобрать, что именно
// прислал MAX, а пользователю — просьба повторить иначе, если в апдейте есть чат.
import type { MiddlewareFn } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { Logger } from '../logger.js';

export const UNREADABLE_TEXT =
  'Не смог прочитать это сообщение. Напишите текстом, пришлите фото, файл или голосовое ещё раз.';

type Shape = Record<string, string>;

function shapeOf(update: Record<string, unknown>): Shape {
  return Object.fromEntries(
    Object.entries(update).map(([key, value]) => {
      if (value === null) return [key, 'null'];
      if (Array.isArray(value)) return [key, `array(${value.length})`];
      if (typeof value === 'object') return [key, `{${Object.keys(value).sort().join(',')}}`];
      return [key, typeof value];
    }),
  );
}

function numberField(update: Record<string, unknown>, key: string): number | undefined {
  const value = update[key];
  return typeof value === 'number' ? value : undefined;
}

export function malformedUpdateGuard(log: Logger): MiddlewareFn<BotContext> {
  return async (ctx, next) => {
    const update = ctx.update as unknown as Record<string, unknown>;
    if (ctx.updateType !== 'message_created' || update.message) return next();
    const chatId = numberField(update, 'chat_id');
    log.warn(
      {
        event: 'bot.update.malformed',
        update_type: ctx.updateType,
        shape: shapeOf(update),
        chat_id: chatId,
        user_id: numberField(update, 'user_id'),
      },
      'message_created without message',
    );
    if (chatId === undefined) return;
    try {
      await ctx.api.sendMessageToChat(chatId, UNREADABLE_TEXT);
    } catch (err) {
      log.warn({ event: 'bot.update.malformed_reply_failed', err }, 'hint not sent');
    }
  };
}
