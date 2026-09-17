// Точка входа бота: конфиг → логгер → Redis → Bot (сессии, middleware,
// хендлеры) → потребитель событий core → polling или webhook → graceful shutdown.
import { hostname } from 'node:os';

import { Bot, session } from '@maxhub/max-bot-api';

import { loadConfig } from './config.js';
import type { BotContext, BotSession } from './context.js';
import { EventConsumer } from './events/consumer.js';
import { coreEventHandlers } from './events/handlers.js';
import { EventPublisher } from './events/publisher.js';
import { registerHandlers } from './handlers/index.js';
import { startHealthServer } from './health.js';
import { createLogger } from './logger.js';
import { loggingMiddleware } from './middlewares/logging.js';
import { createRedis } from './redis.js';
import { RedisSessionStore } from './session/redis-store.js';

// Клиент SDK — голый fetch без таймаута: зависший вызов Bot API остановил бы
// и потребитель событий (обрабатывает последовательно), и polling.
const MAX_API_TIMEOUT_MS = 15_000;
const fetchWithTimeout: typeof fetch = (input, init) =>
  fetch(input, {
    ...init,
    signal: init?.signal
      ? AbortSignal.any([init.signal, AbortSignal.timeout(MAX_API_TIMEOUT_MS)])
      : AbortSignal.timeout(MAX_API_TIMEOUT_MS),
  });

async function main(): Promise<void> {
  const config = loadConfig();
  const log = await createLogger(config);
  log.info({ event: 'bot.starting', mode: config.BOT_MODE, env: config.ENV }, 'starting');

  const redis = createRedis(config, log);
  await redis.connect();

  const bot = new Bot<BotContext>(config.MAX_BOT_TOKEN, {
    clientOptions: { fetch: fetchWithTimeout },
  });
  bot.use(
    session<BotSession, BotContext>({
      store: new RedisSessionStore<BotSession>(redis, {
        ttlSeconds: config.BOT_SESSION_TTL_SECONDS,
      }),
      defaultSession: () => ({ starts: 0 }),
    }),
  );
  bot.use(loggingMiddleware(log));
  bot.catch((err, ctx) => {
    // Ошибка одного апдейта не роняет процесс: пишем в лог и живём дальше.
    log.error({ event: 'bot.handler.error', update_type: ctx.updateType, err }, 'handler failed');
  });

  const publisher = new EventPublisher(redis, log, {
    stream: config.EVENTS_STREAM_TO_CORE,
    maxlen: config.EVENTS_STREAM_MAXLEN,
  });
  registerHandlers(bot, {
    publisher,
    log,
    keyboard: { miniAppName: config.MAX_MINI_APP_NAME },
  });

  // Отдельное соединение для блокирующего XREADGROUP: иначе оно держало бы
  // очередь команд сессий и ответов бота.
  const consumerRedis = createRedis(config, log);
  await consumerRedis.connect();
  const consumer = new EventConsumer(consumerRedis, log, {
    stream: config.EVENTS_STREAM_TO_BOT,
    group: 'bot',
    consumer: `${hostname()}-${process.pid}`,
    handlers: coreEventHandlers(bot, consumerRedis, log),
  });
  await consumer.start();

  const health = startHealthServer(config.BOT_HEALTH_PORT, redis, log);

  const me = await bot.api.getMyInfo();
  await bot.api.setMyCommands([
    { name: 'start', description: 'Главное меню' },
    { name: 'help', description: 'Помощь' },
  ]);
  log.info({ event: 'bot.identity', user_id: me.user_id, username: me.username }, 'bot identity');

  let stopping = false;
  const shutdown = async (signal: string) => {
    if (stopping) return;
    stopping = true;
    log.info({ event: 'bot.stopping', signal }, 'stopping');
    // В webhook-режиме подписку в MAX не снимаем: пока контейнер перезапускается,
    // платформа копит апдейты и доставит их новому процессу. stopWebhook() сделал
    // бы unsubscribe, и всё за время рестарта пропало бы.
    if (config.BOT_MODE === 'polling') bot.stopPolling();
    await consumer.stop();
    health.close();
    await Promise.all([redis.quit(), consumerRedis.quit()]);
    log.info({ event: 'bot.stopped' }, 'stopped');
    log.flush();
    setTimeout(() => process.exit(0), 100);
  };
  // Обработчики ставятся ДО запуска: в polling-режиме bot.start() не возвращается,
  // пока polling не остановлен, и код после него не выполнился бы.
  process.once('SIGINT', () => void shutdown('SIGINT'));
  process.once('SIGTERM', () => void shutdown('SIGTERM'));

  const allowedUpdates = ['bot_started', 'message_created', 'message_callback'] as const;
  if (config.BOT_MODE === 'webhook') {
    await bot.start({
      mode: 'webhook',
      options: {
        domain: config.PUBLIC_BASE_URL,
        path: config.BOT_WEBHOOK_PATH,
        port: config.BOT_WEBHOOK_PORT,
        secret: config.BOT_WEBHOOK_SECRET,
        allowedUpdates: [...allowedUpdates],
      },
    });
    log.info({ event: 'bot.webhook.started', path: config.BOT_WEBHOOK_PATH }, 'webhook mode');
  } else {
    log.info({ event: 'bot.polling.started' }, 'polling mode');
    // Промис живёт, пока крутится polling; резолв без stopPolling — SDK сдался.
    await bot.start({ mode: 'polling', options: { allowedUpdates: [...allowedUpdates] } });
    if (!stopping) {
      log.error({ event: 'bot.polling.exited' }, 'polling loop exited unexpectedly');
      process.exit(1);
    }
  }
}

main().catch((err: unknown) => {
  // Логгер мог не создаться (невалидный конфиг) — пишем в stderr напрямую.
  process.stderr.write(`${err instanceof Error ? (err.stack ?? err.message) : String(err)}\n`);
  process.exit(1);
});
