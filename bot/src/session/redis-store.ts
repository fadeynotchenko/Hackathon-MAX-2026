// Хранилище сессий в Redis: бот переживает рестарт и может работать в
// нескольких экземплярах (MemorySessionStore из SDK — только для разработки).
import type { AsyncSessionStore } from '@maxhub/max-bot-api';

// Минимальный интерфейс клиента: ровно то, что нужно хранилищу. Так тесты
// подставляют простой объект, а прод — ioredis.
export interface KeyValueClient {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, mode: 'EX', ttlSeconds: number): Promise<unknown>;
  del(key: string): Promise<unknown>;
}

export interface RedisSessionStoreOptions {
  prefix?: string;
  ttlSeconds: number;
}

export class RedisSessionStore<T extends object> implements AsyncSessionStore<T> {
  private readonly prefix: string;
  private readonly ttlSeconds: number;

  constructor(
    private readonly client: KeyValueClient,
    options: RedisSessionStoreOptions,
  ) {
    this.prefix = options.prefix ?? 'bot:session:';
    this.ttlSeconds = options.ttlSeconds;
  }

  async get(key: string): Promise<T | undefined> {
    const raw = await this.client.get(this.prefix + key);
    if (raw === null) return undefined;
    try {
      return JSON.parse(raw) as T;
    } catch {
      // Битая запись не должна ронять обработку апдейта: сессия начнётся заново.
      await this.client.del(this.prefix + key);
      return undefined;
    }
  }

  async set(key: string, value: T): Promise<void> {
    await this.client.set(this.prefix + key, JSON.stringify(value), 'EX', this.ttlSeconds);
  }

  async delete(key: string): Promise<void> {
    await this.client.del(this.prefix + key);
  }
}
