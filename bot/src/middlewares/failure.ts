// Последний рубеж для ошибки обработчика: процесс живёт дальше, ошибка — в логе,
// а пользователь получает ответ вместо тишины. Контекст может быть битым (так
// падало голосовое), поэтому даже чтение chatId завёрнуто в try.
import type { BotContext } from '../context.js';
import type { Logger } from '../logger.js';

export const FAILURE_TEXT = 'Что-то пошло не так. Повторите, пожалуйста, ещё раз.';

export function handlerFailure(log: Logger): (err: unknown, ctx: BotContext) => Promise<void> {
  return async (err, ctx) => {
    log.error({ event: 'bot.handler.error', update_type: ctx.updateType, err }, 'handler failed');
    try {
      if (ctx.chatId !== undefined && ctx.chatId !== null) await ctx.reply(FAILURE_TEXT);
    } catch (replyErr) {
      log.warn({ event: 'bot.handler.error_reply_failed', err: replyErr }, 'failure not reported');
    }
  };
}
