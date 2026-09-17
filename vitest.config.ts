// Корневая конфигурация: один `pnpm test` гоняет оба воркспейса.
// Настройки окружения (node для бота, jsdom для веба) — в их vitest.config.ts.
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    projects: ['bot', 'web'],
  },
});
