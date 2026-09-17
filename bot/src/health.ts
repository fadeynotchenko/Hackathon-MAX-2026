// HTTP /health для docker healthcheck: 200, если бот запущен и Redis отвечает.
import { createServer, type Server } from 'node:http';

import type { Redis } from 'ioredis';

import type { Logger } from './logger.js';

export function startHealthServer(port: number, redis: Redis, log: Logger): Server {
  const server = createServer((req, res) => {
    if (req.url !== '/health') {
      res.writeHead(404).end();
      return;
    }
    redis
      .ping()
      .then(() => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok', checks: { redis: 'ok' } }));
      })
      .catch((err: unknown) => {
        log.warn({ event: 'health.check_failed', component: 'redis', err }, 'health degraded');
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'degraded', checks: { redis: 'error' } }));
      });
  });
  server.listen(port, () => log.info({ event: 'health.listening', port }, 'health server up'));
  return server;
}
