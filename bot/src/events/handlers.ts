// Обработчики событий core → бот.
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { Keyboard, type Bot } from '@maxhub/max-bot-api';
import type { Redis } from 'ioredis';

import type { BotContext } from '../context.js';
import type { Logger } from '../logger.js';
import {
  DOCUMENT_READY,
  DocumentReady,
  NOTIFY_USER,
  NotifyUser,
  type InlineButton,
} from './codec.js';
import { HandlerRejected, type Handler } from './consumer.js';

// Коды MAX Bot API, при которых повторять доставку бессмысленно.
const PERMANENT_STATUSES = new Set([400, 403, 404]);
// Сколько помнить доставленные события: дольше, чем событие может висеть pending.
const DELIVERED_TTL_SECONDS = 7 * 24 * 3600;
// Файл документа небольшой (DOCX/PDF на страницу), но сеть может залипнуть.
const DOWNLOAD_TIMEOUT_MS = 30_000;

// Кнопки из ядра — только callback: действие решает ядро, бот лишь возвращает payload.
export function buttonsKeyboard(rows: InlineButton[][]) {
  return Keyboard.inlineKeyboard(
    rows.map((row) => row.map((button) => Keyboard.button.callback(button.text, button.payload))),
  );
}

export interface CoreEventDeps {
  coreApiUrl: string;
}

export function coreEventHandlers(
  bot: Bot<BotContext>,
  redis: Redis,
  log: Logger,
  deps: CoreEventDeps,
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
          ...(data.buttons?.length ? { attachments: [buttonsKeyboard(data.buttons)] } : {}),
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

    [DOCUMENT_READY]: async (event) => {
      const data = DocumentReady.parse(event.payload);
      const marker = await redis.set(
        `events:delivered:${event.id}`,
        '1',
        'EX',
        DELIVERED_TTL_SECONDS,
        'NX',
      );
      if (marker === null) {
        log.info({ event: 'document.duplicate', event_id: event.id }, 'already delivered');
        return;
      }

      let response: Response;
      try {
        response = await fetch(
          `${deps.coreApiUrl}/api/v1/documents/download/${data.download_token}`,
          { signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS) },
        );
      } catch (err) {
        // Сеть до ядра — временная беда: снимаем отметку, событие переиграется.
        await redis.del(`events:delivered:${event.id}`);
        throw err;
      }
      if (!response.ok) {
        // Токен одноразовый: 404 значит «уже использован или истёк», повтор не поможет.
        if (response.status === 404) {
          throw new HandlerRejected(
            `ядро не отдало файл: ${response.status}`,
            'document.token_invalid',
          );
        }
        await redis.del(`events:delivered:${event.id}`);
        throw new Error(`core ${response.status} при скачивании документа`);
      }

      const buffer = Buffer.from(await response.arrayBuffer());
      // SDK берёт имя файла из пути; для Buffer оно было бы случайным UUID,
      // и пользователь получил бы в чат файл с именем-идентификатором.
      const dir = await mkdtemp(join(tmpdir(), 'maxapp-doc-'));
      const path = join(dir, data.filename);
      try {
        await writeFile(path, buffer);
        const attachment = await bot.api.uploadFile({ source: path });
        await bot.api.sendMessageToUser(data.max_user_id, data.text, {
          attachments: [attachment.toJson()],
        });
      } catch (err) {
        // Токен уже сгорел на скачивании, повторять событие нечем: помечаем
        // окончательным, пользователь нажмёт «отправить» ещё раз.
        const status = (err as { status?: number }).status;
        throw new HandlerRejected(
          `не удалось отправить документ: ${status ?? (err as Error).message}`,
          'document.send_failed',
        );
      } finally {
        await rm(dir, { recursive: true, force: true });
      }

      log.info(
        {
          event: 'document.delivered',
          max_user_id: data.max_user_id,
          document_id: data.document_id,
          format: data.format,
          size: data.size,
          event_id: event.id,
        },
        'document sent',
      );
    },
  };
}
