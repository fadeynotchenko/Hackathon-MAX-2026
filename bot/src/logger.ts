// Логгер бота: pino с той же JSON-схемой, что у core (core.logs.setup):
// ts, level, service, logger, event, msg, поля, err.
//
// Потоки собираются in-process через pino.multistream, а не pino.transport:
// у транспорта в воркере уровень берётся из уже сериализованной строки, и
// строковая метка уровня (нужна для общей схемы с Python) ломала фильтрацию —
// бот молчал во всех потоках. Пишет в stdout (JSON вне терминала, pino-pretty
// в терминале) и, если LOG_DIR задан, в файл LOG_DIR/bot.<дата>.N.log (pino-roll).
import { join } from 'node:path';

import pino, { type Logger, type StreamEntry } from 'pino';
import pinoPretty from 'pino-pretty';
import pinoRoll from 'pino-roll';

import type { BotConfig } from './config.js';

export type { Logger };

type LoggerConfig = Pick<BotConfig, 'LOG_LEVEL' | 'LOG_FORMAT' | 'LOG_DIR'>;

function resolveFormat(format: LoggerConfig['LOG_FORMAT']): 'json' | 'pretty' {
  if (format !== 'auto') return format;
  return process.stdout.isTTY ? 'pretty' : 'json';
}

// Тот же словарь уровней, что у Python logging: warn → warning.
const LEVEL_LABELS: Record<string, string> = { warn: 'warning' };

export async function createLogger(config: LoggerConfig): Promise<Logger> {
  if (config.LOG_LEVEL === 'silent') return silentLogger();
  const level = config.LOG_LEVEL;
  const streams: StreamEntry[] = [];
  streams.push({
    level,
    stream:
      resolveFormat(config.LOG_FORMAT) === 'pretty'
        ? pinoPretty({
            translateTime: 'SYS:HH:MM:ss.l',
            ignore: 'service,logger',
            messageFormat: '{service} {event} {msg}',
          })
        : process.stdout,
  });
  if (config.LOG_DIR) {
    streams.push({
      level,
      stream: await pinoRoll({
        file: join(config.LOG_DIR, 'bot'),
        frequency: 'daily',
        extension: '.log',
        dateFormat: 'yyyy-MM-dd',
        mkdir: true,
      }),
    });
  }
  return pino(
    {
      level,
      base: { service: 'bot' },
      messageKey: 'msg',
      timestamp: () => `,"ts":"${new Date().toISOString()}"`,
      formatters: { level: (label) => ({ level: LEVEL_LABELS[label] ?? label }) },
    },
    pino.multistream(streams),
  );
}

// Для тестов и мест, где вывод не нужен.
export function silentLogger(): Logger {
  return pino({ level: 'silent' });
}
