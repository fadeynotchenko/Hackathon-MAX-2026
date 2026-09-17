// Потребитель стрима ядро → бот (EVENTS_STREAM_TO_BOT) через consumer group.
//
// Тот же протокол, что у core.events.bus на стороне Python:
//   XAUTOCLAIM зависших у упавших потребителей → XREADGROUP новых → обработчик → XACK.
// Окончательные ошибки (битый конверт, невалидный payload, HandlerRejected)
// подтверждаются сразу; временные остаются pending и переигрываются, пока не
// упрутся в maxDeliveries — тогда ack + events.handler.dropped.
import { setImmediate as yieldToLoop } from 'node:timers/promises';

import type { Redis } from 'ioredis';
import { ZodError } from 'zod';

import type { Logger } from '../logger.js';
import { EventDecodeError, decodeEvent, type Event } from './codec.js';

export type Handler = (event: Event) => Promise<void>;

// Обработчик бросает это, когда повтор не поможет (пользователь заблокировал бота и т.п.).
export class HandlerRejected extends Error {
  constructor(
    message: string,
    readonly code: string,
  ) {
    super(message);
    this.name = 'HandlerRejected';
  }
}

export interface ConsumerOptions {
  stream: string;
  group: string;
  consumer: string;
  handlers: Record<string, Handler>;
  blockMs?: number;
  batch?: number;
  staleAfterMs?: number;
  maxDeliveries?: number;
}

type StreamEntry = [id: string, fields: string[]];

function toRecord(flat: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (let i = 0; i + 1 < flat.length; i += 2) out[flat[i]!] = flat[i + 1]!;
  return out;
}

export class EventConsumer {
  private readonly blockMs: number;
  private readonly batch: number;
  private readonly staleAfterMs: number;
  private readonly maxDeliveries: number;
  private running = false;
  private loop: Promise<void> | null = null;

  constructor(
    private readonly redis: Redis,
    private readonly log: Logger,
    private readonly options: ConsumerOptions,
  ) {
    this.blockMs = options.blockMs ?? 5000;
    this.batch = options.batch ?? 32;
    this.staleAfterMs = options.staleAfterMs ?? 60_000;
    this.maxDeliveries = options.maxDeliveries ?? 5;
  }

  async start(): Promise<void> {
    await this.ensureGroup();
    this.running = true;
    this.log.info(
      { event: 'events.consumer.started', stream: this.options.stream, group: this.options.group },
      'consumer started',
    );
    this.loop = this.run();
  }

  async stop(): Promise<void> {
    this.running = false;
    await this.loop;
    this.log.info(
      { event: 'events.consumer.stopped', stream: this.options.stream },
      'consumer stopped',
    );
  }

  private async ensureGroup(): Promise<void> {
    try {
      await this.redis.xgroup('CREATE', this.options.stream, this.options.group, '0', 'MKSTREAM');
    } catch (err) {
      if (!(err instanceof Error) || !err.message.includes('BUSYGROUP')) throw err;
    }
  }

  private async run(): Promise<void> {
    const { stream, group, consumer } = this.options;
    while (this.running) {
      try {
        const claimed = (await this.redis.xautoclaim(
          stream,
          group,
          consumer,
          this.staleAfterMs,
          '0-0',
          'COUNT',
          this.batch,
        )) as [string, StreamEntry[], string[]];
        const entries = claimed[1] ?? [];
        const deliveries = await this.deliveryCounts(entries);
        for (const [id, flat] of entries) {
          await this.handle(id, toRecord(flat), deliveries.get(id) ?? 1);
        }

        const response = (await this.redis.xreadgroup(
          'GROUP',
          group,
          consumer,
          'COUNT',
          this.batch,
          'BLOCK',
          this.blockMs,
          'STREAMS',
          stream,
          '>',
        )) as [string, StreamEntry[]][] | null;
        for (const [, streamEntries] of response ?? []) {
          for (const [id, flat] of streamEntries) await this.handle(id, toRecord(flat), 1);
        }
        // Пустой опрос: отдать очередь макрозадачам (таймеры, сигналы). Настоящий
        // Redis блокирует XREADGROUP на blockMs, а клиент без блокировки (тесты)
        // иначе превратил бы цикл в busy-loop без единого тика event loop.
        if (entries.length === 0 && !response) await yieldToLoop();
      } catch (err) {
        if (!this.running) break;
        this.log.warn({ event: 'events.consumer.error', err }, 'consumer loop error');
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    }
  }

  private async deliveryCounts(entries: StreamEntry[]): Promise<Map<string, number>> {
    const counts = new Map<string, number>();
    if (entries.length === 0) return counts;
    // После XAUTOCLAIM записи принадлежат этому consumer'у: фильтр по нему не даёт
    // чужим pending-записям в том же диапазоне вытеснить наши из ответа.
    const rows = (await this.redis.xpending(
      this.options.stream,
      this.options.group,
      entries[0]![0],
      entries[entries.length - 1]![0],
      entries.length,
      this.options.consumer,
    )) as [string, string, number, number][];
    for (const [id, , , times] of rows) counts.set(id, times);
    return counts;
  }

  private async ack(id: string): Promise<void> {
    await this.redis.xack(this.options.stream, this.options.group, id);
  }

  private async handle(
    streamId: string,
    fields: Record<string, string>,
    deliveries: number,
  ): Promise<void> {
    let event: Event;
    try {
      event = decodeEvent(streamId, fields);
    } catch (err) {
      await this.ack(streamId);
      this.log.error(
        {
          event: 'events.bad_envelope',
          stream_id: streamId,
          err: err instanceof EventDecodeError ? err.message : err,
        },
        'bad envelope',
      );
      return;
    }
    const handler = this.options.handlers[event.type];
    if (!handler) {
      await this.ack(streamId);
      return;
    }
    try {
      await handler(event);
    } catch (err) {
      if (err instanceof ZodError || err instanceof HandlerRejected) {
        await this.ack(streamId);
        this.log.error(
          { event: 'events.handler.rejected', type: event.type, event_id: event.id, err },
          'event rejected',
        );
        return;
      }
      if (deliveries >= this.maxDeliveries) {
        await this.ack(streamId);
        this.log.error(
          { event: 'events.handler.dropped', type: event.type, event_id: event.id, deliveries },
          'event dropped after max deliveries',
        );
      } else {
        this.log.error(
          { event: 'events.handler.failed', type: event.type, event_id: event.id, deliveries, err },
          'handler failed, will retry',
        );
      }
      return;
    }
    await this.ack(streamId);
    this.log.info(
      { event: 'events.handled', type: event.type, event_id: event.id, source: event.source },
      'event handled',
    );
  }
}
