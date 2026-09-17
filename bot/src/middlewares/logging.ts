// Одна запись на апдейт: тип, пользователь, чат, длительность. Ошибки
// обработчиков ловит bot.catch в main.ts — здесь только журнал.
import type { MiddlewareFn } from '@maxhub/max-bot-api';

import type { BotContext } from '../context.js';
import type { Logger } from '../logger.js';

export function loggingMiddleware(log: Logger): MiddlewareFn<BotContext> {
  return async (ctx, next) => {
    const started = performance.now();
    try {
      await next();
    } finally {
      log.info(
        {
          event: 'bot.update',
          update_type: ctx.updateType,
          user_id: ctx.user?.user_id,
          chat_id: ctx.chatId ?? undefined,
          duration_ms: Math.round((performance.now() - started) * 10) / 10,
        },
        'update handled',
      );
    }
  };
}
