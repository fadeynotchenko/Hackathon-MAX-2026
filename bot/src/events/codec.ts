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
export const BOT_MESSAGE = 'bot.message';
export const BOT_CALLBACK = 'bot.callback';
export const BOT_ATTACHMENT = 'bot.attachment';
export const BOT_DOCUMENT_DELIVERY = 'bot.document_delivery';

// Кнопка под сообщением: нажатие уходит обратно в ядро событием bot.callback.
export const InlineButton = z.strictObject({
  text: z.string().min(1).max(64),
  payload: z.string().min(1).max(128),
});
export type InlineButton = z.infer<typeof InlineButton>;

// Ядро → бот: отправить пользователю сообщение в MAX.
export const NotifyUser = z.strictObject({
  max_user_id: z.number().int().positive(),
  text: z.string().min(1).max(4000),
  format: z.enum(['markdown', 'html']).nullable().default(null),
  buttons: z.array(z.array(InlineButton)).nullable().default(null),
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

// Бот → ядро: пользователь написал боту текст, а не команду.
export const BotMessage = z.strictObject({
  max_user_id: z.number().int().positive(),
  chat_id: z.number().int(),
  text: z.string().min(1).max(4000),
  first_name: z.string().default(''),
  last_name: z.string().nullable().default(null),
  username: z.string().nullable().default(null),
});
export type BotMessage = z.infer<typeof BotMessage>;

// Бот → ядро: пользователь нажал кнопку, присланную ядром.
export const BotCallback = z.strictObject({
  max_user_id: z.number().int().positive(),
  chat_id: z.number().int(),
  payload: z.string().min(1).max(128),
});
export type BotCallback = z.infer<typeof BotCallback>;

// Бот → ядро: пользователь прислал фото, файл или голосовое. Байты не в событии:
// ядро скачивает файл по ссылке MAX само. text — подпись к вложению.
export const BotAttachment = z.strictObject({
  max_user_id: z.number().int().positive(),
  chat_id: z.number().int(),
  kind: z.enum(['image', 'file', 'audio']),
  url: z.string().min(9).max(2048).startsWith('https://'),
  filename: z.string().max(255).nullable().default(null),
  size: z.number().int().nonnegative().nullable().default(null),
  text: z.string().max(4000).nullable().default(null),
  first_name: z.string().default(''),
  last_name: z.string().nullable().default(null),
  username: z.string().nullable().default(null),
});
export type BotAttachment = z.infer<typeof BotAttachment>;

// Бот → ядро: чем закончилась доставка файла из document.ready. event_id — UUID
// того события: по нему ядро сшивает доставку с отправкой в журнале фактов.
export const BotDocumentDelivery = z.strictObject({
  max_user_id: z.number().int().positive(),
  document_id: z.number().int().positive(),
  event_id: z.string().min(1).max(64),
  format: z.enum(['docx', 'pdf']),
  status: z.enum(['delivered', 'failed']),
  error: z.string().max(64).nullable().default(null),
});
export type BotDocumentDelivery = z.infer<typeof BotDocumentDelivery>;

export const EVENT_PAYLOADS = {
  [NOTIFY_USER]: NotifyUser,
  [DOCUMENT_READY]: DocumentReady,
  [BOT_USER_STARTED]: BotUserStarted,
  [BOT_MESSAGE]: BotMessage,
  [BOT_CALLBACK]: BotCallback,
  [BOT_ATTACHMENT]: BotAttachment,
  [BOT_DOCUMENT_DELIVERY]: BotDocumentDelivery,
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
  // Входной тип схемы, а не выходной: поля со значением по умолчанию
  // (buttons, format) можно не передавать — их подставит принимающая сторона.
  payload: z.input<(typeof EVENT_PAYLOADS)[EventType]>,
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
