// Контракт событий между ботом и Python-ядром (Redis Streams).
//
// Источник правды — сервис core (core.events.contracts); его JSON Schema лежит
// в contracts/events.schema.json, и codec.test.ts сверяет zod-схемы ниже с ней:
// набор событий, обязательные поля, версия конверта. Менять поле здесь без
// правки контракта в core нельзя — тест это поймает.
import { randomUUID } from 'node:crypto';

import { z } from 'zod';

export const ENVELOPE_VERSION = 1;

export const NOTIFY_USER = 'notify.user';
export const DOCUMENT_READY = 'document.ready';
export const BOT_USER_STARTED = 'bot.user_started';

// Ядро → бот: отправить пользователю сообщение в MAX.
export const NotifyUser = z.strictObject({
  max_user_id: z.number().int().positive(),
  text: z.string().min(1).max(4000),
  format: z.enum(['markdown', 'html']).nullable().default(null),
});
export type NotifyUser = z.infer<typeof NotifyUser>;

// Ядро → бот: отдать пользователю готовый файл документа.
export const DocumentReady = z.strictObject({
  max_user_id: z.number().int().positive(),
  document_id: z.number().int().positive(),
  title: z.string().min(1).max(255),
  filename: z.string().min(1).max(255),
  format: z.enum(['docx', 'pdf']),
  size: z.number().int().positive(),
  download_token: z.string().min(16).max(128),
  text: z.string().min(1).max(4000),
});
export type DocumentReady = z.infer<typeof DocumentReady>;

// Бот → ядро: пользователь нажал «Начать».
export const BotUserStarted = z.strictObject({
  max_user_id: z.number().int().positive(),
  chat_id: z.number().int(),
  first_name: z.string().default(''),
  last_name: z.string().nullable().default(null),
  username: z.string().nullable().default(null),
  language_code: z.string().nullable().default(null),
  start_payload: z.string().nullable().default(null),
});
export type BotUserStarted = z.infer<typeof BotUserStarted>;

export const EVENT_PAYLOADS = {
  [NOTIFY_USER]: NotifyUser,
  [DOCUMENT_READY]: DocumentReady,
  [BOT_USER_STARTED]: BotUserStarted,
} as const;

export type EventType = keyof typeof EVENT_PAYLOADS;

// Поля записи стрима — всегда строки (так их отдаёт Redis).
export const Envelope = z.object({
  id: z.string().min(1),
  v: z.coerce.number().int(),
  type: z.string().min(1),
  payload: z.string(),
  ts: z.string(),
  source: z.string(),
});

export interface Event<T = unknown> {
  id: string;
  v: number;
  type: string;
  payload: T;
  ts: string;
  source: string;
  streamId: string;
}

export class EventDecodeError extends Error {
  constructor(
    message: string,
    readonly streamId: string,
  ) {
    super(message);
    this.name = 'EventDecodeError';
  }
}

// Запись стрима → конверт с разобранным payload. Fail-fast: битая запись —
// EventDecodeError, потребитель подтверждает её и пишет в лог.
export function decodeEvent(streamId: string, fields: Record<string, string>): Event {
  const parsed = Envelope.safeParse(fields);
  if (!parsed.success) {
    throw new EventDecodeError(
      `конверт не разбирается: ${z.prettifyError(parsed.error)}`,
      streamId,
    );
  }
  let payload: unknown;
  try {
    payload = JSON.parse(parsed.data.payload);
  } catch {
    throw new EventDecodeError('payload не JSON', streamId);
  }
  if (payload === null || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new EventDecodeError('payload не объект', streamId);
  }
  return { ...parsed.data, payload, streamId };
}

// Конверт для XADD. Порядок полей тот же, что у Python (удобно читать XRANGE).
export function encodeEvent(
  type: EventType,
  payload: z.infer<(typeof EVENT_PAYLOADS)[EventType]>,
  source: string,
  now: Date,
): { id: string; fields: Record<string, string> } {
  const id = randomUUID().replaceAll('-', '');
  return {
    id,
    fields: {
      id,
      v: String(ENVELOPE_VERSION),
      type,
      payload: JSON.stringify(payload),
      ts: now.toISOString(),
      source,
    },
  };
}
