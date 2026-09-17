// Публикация событий бот → ядро (XADD в EVENTS_STREAM_TO_CORE).
import type { Redis } from 'ioredis';

import type { Logger } from '../logger.js';
import { BOT_USER_STARTED, encodeEvent, type BotUserStarted } from './codec.js';

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

  async userStarted(payload: BotUserStarted): Promise<string> {
    const { id, fields } = encodeEvent(
      BOT_USER_STARTED,
      payload,
      this.options.source ?? 'bot',
      new Date(),
    );
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
      { event: 'events.published', type: BOT_USER_STARTED, event_id: id, stream_id: streamId },
      'event published',
    );
    return id;
  }
}
