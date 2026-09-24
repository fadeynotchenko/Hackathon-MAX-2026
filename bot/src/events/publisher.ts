// Публикация событий бот → ядро (XADD в EVENTS_STREAM_TO_CORE).
import type { Redis } from 'ioredis';

import type { Logger } from '../logger.js';
import {
  BOT_ATTACHMENT,
  BOT_CALLBACK,
  BOT_DOCUMENT_DELIVERY,
  BOT_MESSAGE,
  BOT_USER_STARTED,
  encodeEvent,
  type BotAttachment,
  type BotCallback,
  type BotDocumentDelivery,
  type BotMessage,
  type BotUserStarted,
  type EventType,
} from './codec.js';

export interface PublisherOptions {
  stream: string;
  maxlen: number;
  source?: string;
}

export class EventPublisher {
  constructor(
    private readonly redis: Redis,
    private readonly log: Logger,
    private readonly options: PublisherOptions,
  ) {}

  userStarted(payload: BotUserStarted): Promise<string> {
    return this.publish(BOT_USER_STARTED, payload);
  }

  message(payload: BotMessage): Promise<string> {
    return this.publish(BOT_MESSAGE, payload);
  }

  callback(payload: BotCallback): Promise<string> {
    return this.publish(BOT_CALLBACK, payload);
  }

  attachment(payload: BotAttachment): Promise<string> {
    return this.publish(BOT_ATTACHMENT, payload);
  }

  documentDelivery(payload: BotDocumentDelivery): Promise<string> {
    return this.publish(BOT_DOCUMENT_DELIVERY, payload);
  }

  private async publish(
    type: EventType,
    payload: BotUserStarted | BotMessage | BotCallback | BotAttachment | BotDocumentDelivery,
  ): Promise<string> {
    const { id, fields } = encodeEvent(type, payload, this.options.source ?? 'bot', new Date());
    // MAXLEN ~ : приблизительное усечение дешевле точного, стрим не растёт бесконечно.
    const streamId = await this.redis.xadd(
      this.options.stream,
      'MAXLEN',
      '~',
      this.options.maxlen,
      '*',
      ...Object.entries(fields).flat(),
    );
    this.log.info(
      { event: 'events.published', type, event_id: id, stream_id: streamId },
      'event published',
    );
    return id;
  }
}
