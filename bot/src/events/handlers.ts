// Обработчики событий core → бот.
import type { Bot } from '@maxhub/max-bot-api';
import type { Redis } from 'ioredis';

import type { BotContext } from '../context.js';
import type { Logger } from '../logger.js';
import { NOTIFY_USER, NotifyUser } from './codec.js';
import { HandlerRejected, type Handler } from './consumer.js';

// Коды MAX Bot API, при которых повторять доставку бессмысленно.
const PERMANENT_STATUSES = new Set([400, 403, 404]);
// Сколько помнить доставленные события: дольше, чем событие может висеть pending.
const DELIVERED_TTL_SECONDS = 7 * 24 * 3600;

export function coreEventHandlers(
  bot: Bot<BotContext>,
  redis: Redis,
  log: Logger,
): Record<string, Handler> {
  return {
    [NOTIFY_USER]: async (event) => {
      // ZodError на битом payload — окончательная ошибка, потребитель подтвердит событие.
      const data = NotifyUser.parse(event.payload);
      // Идемпотентность по Event.id: повторная доставка (XACK не дошёл, перехват
      // XAUTOCLAIM, рестарт) не должна слать пользователю второе сообщение.
      const marker = await redis.set(
        `events:delivered:${event.id}`,
        '1',
        'EX',
        DELIVERED_TTL_SECONDS,
        'NX',
      );
      if (marker === null) {
        log.info({ event: 'notify.duplicate', event_id: event.id }, 'already delivered');
        return;
      }
      try {
        await bot.api.sendMessageToUser(data.max_user_id, data.text, {
          ...(data.format ? { format: data.format } : {}),
        });
      } catch (err) {
        // Отправка не состоялась — снимаем отметку, чтобы повтор был возможен.
        await redis.del(`events:delivered:${event.id}`);
        const status = (err as { status?: number }).status;
        if (status !== undefined && PERMANENT_STATUSES.has(status)) {
          throw new HandlerRejected(
            `MAX API ${status}: пользователь недоступен`,
            `max_api.${status}`,
          );
        }
        throw err;
      }
      log.info(
        { event: 'notify.delivered', max_user_id: data.max_user_id, event_id: event.id },
        'notified',
      );
    },
  };
}
