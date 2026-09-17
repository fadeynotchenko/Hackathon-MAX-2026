import { Redis } from 'ioredis';

import type { BotConfig } from './config.js';
import type { Logger } from './logger.js';

type RedisConfig = Pick<BotConfig, 'REDIS_HOST' | 'REDIS_PORT' | 'REDIS_PASSWORD' | 'REDIS_DB'>;

// lazyConnect: соединение открывается явно в main(), чтобы ошибка подключения
// была ошибкой старта, а не тихим reconnect-циклом в фоне.
export function createRedis(config: RedisConfig, log: Logger): Redis {
  const redis = new Redis({
    host: config.REDIS_HOST,
    port: config.REDIS_PORT,
    db: config.REDIS_DB,
    ...(config.REDIS_PASSWORD ? { password: config.REDIS_PASSWORD } : {}),
    lazyConnect: true,
    maxRetriesPerRequest: 3,
  });
  redis.on('error', (err: Error) => log.error({ event: 'redis.error', err }, 'redis error'));
  return redis;
}
