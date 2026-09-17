import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    name: 'bot',
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
