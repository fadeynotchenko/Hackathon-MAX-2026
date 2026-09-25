// Конфиг бота: единственное место, где читается process.env.
//
// Имена переменных описаны в реестре core/src/core/config/env_spec.py (тест-замок
// core/tests/config/test_env_spec.py сверяет объявления ниже с реестром).
// Схема zod валидирует типы на старте: бот с неполным окружением не поднимется.
import { resolve } from 'node:path';

import { config as loadDotenv } from 'dotenv';
import { z } from 'zod';

// Локальный запуск читает .env из корня репозитория. В compose переменные
// приходят из env_file и имеют приоритет: dotenv не перекрывает заданное.
loadDotenv({
  path: [resolve(process.cwd(), '..', '.env'), resolve(process.cwd(), '.env')],
  quiet: true,
});

const schema = z
  .object({
    ENV: z.enum(['dev', 'production']).default('dev'),
    // Тот же словарь, что у Python logging: WARNING/CRITICAL допустимы, pino их не знает.
    LOG_LEVEL: z
      .string()
      .default('info')
      .transform((value) => value.toLowerCase())
      .transform((value) => ({ warning: 'warn', critical: 'fatal' })[value] ?? value)
      .pipe(z.enum(['trace', 'debug', 'info', 'warn', 'error', 'fatal', 'silent'])),
    LOG_FORMAT: z.enum(['auto', 'json', 'pretty']).default('auto'),
    LOG_DIR: z.string().default('app_logs'),
    PUBLIC_BASE_URL: z.string().default(''),
    MAX_BOT_TOKEN: z.string().min(1, 'MAX_BOT_TOKEN обязателен'),
    MAX_MINI_APP_NAME: z.string().default(''),
    BOT_MODE: z.enum(['polling', 'webhook']).default('polling'),
    BOT_POLLING_TAKEOVER: z.stringbool().default(false),
    BOT_WEBHOOK_PATH: z.string().startsWith('/').default('/bot/webhook'),
    BOT_WEBHOOK_SECRET: z.string().default(''),
    BOT_WEBHOOK_PORT: z.coerce.number().int().positive().default(8080),
    BOT_HEALTH_PORT: z.coerce.number().int().positive().default(8081),
    BOT_SESSION_TTL_SECONDS: z.coerce.number().int().positive().default(604800),
    REDIS_HOST: z.string().default('redis'),
    REDIS_PORT: z.coerce.number().int().positive().default(6379),
    REDIS_PASSWORD: z.string().default(''),
    REDIS_DB: z.coerce.number().int().min(0).default(0),
    // Адрес ядра внутри стека: бот забирает файлы документов по одноразовому токену.
    CORE_INTERNAL_URL: z.string().url().default('http://api:8000'),
    EVENTS_STREAM_TO_BOT: z.string().default('maxapp:to_bot'),
    EVENTS_STREAM_TO_CORE: z.string().default('maxapp:to_core'),
    EVENTS_STREAM_MAXLEN: z.coerce.number().int().positive().default(10000),
  })
  .superRefine((cfg, ctx) => {
    // Плейсхолдеры из .env.example годятся для локали, но не для production.
    if (cfg.ENV === 'production') {
      for (const key of ['MAX_BOT_TOKEN', 'BOT_WEBHOOK_SECRET', 'REDIS_PASSWORD'] as const) {
        if (cfg[key].startsWith('dev-only-')) {
          ctx.addIssue({
            code: 'custom',
            path: [key],
            message: 'dev-плейсхолдер из .env.example в production',
          });
        }
      }
    }
    if (cfg.BOT_MODE !== 'webhook') return;
    if (!cfg.PUBLIC_BASE_URL.startsWith('https://')) {
      ctx.addIssue({
        code: 'custom',
        path: ['PUBLIC_BASE_URL'],
        message: 'в режиме webhook нужен публичный https-адрес',
      });
    }
    if (cfg.BOT_WEBHOOK_SECRET.length < 16) {
      ctx.addIssue({
        code: 'custom',
        path: ['BOT_WEBHOOK_SECRET'],
        message: 'в режиме webhook секрет обязателен (16+ символов)',
      });
    }
  });

export type BotConfig = z.infer<typeof schema>;

export function loadConfig(env: NodeJS.ProcessEnv = process.env): BotConfig {
  // Пустая строка в .env (PUBLIC_BASE_URL=) означает «не задано», а не значение.
  // Исключение — LOG_DIR: явно пустой выключает файловый лог (как в core).
  const present = Object.fromEntries(
    Object.entries(env).filter(
      ([key, value]) => value !== undefined && (value !== '' || key === 'LOG_DIR'),
    ),
  );
  const result = schema.safeParse(present);
  if (!result.success) {
    throw new Error(`Некорректное окружение бота:\n${z.prettifyError(result.error)}`);
  }
  return result.data;
}
