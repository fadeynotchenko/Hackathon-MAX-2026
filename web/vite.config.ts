// Vite: dev-сервер мини-аппа. /api/ проксируется в бэкенд (VITE_PROXY_TARGET),
// поэтому в dev фронт и API живут на одном origin, как в проде за nginx.
import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

const projectRoot = path.resolve(import.meta.dirname, '..');

export default defineConfig(({ mode }) => {
  // .env читается из корня репозитория: одна точка правды для всех сервисов.
  const env = loadEnv(mode, projectRoot, 'VITE_');
  const proxyTarget =
    process.env['VITE_PROXY_TARGET'] ?? env['VITE_PROXY_TARGET'] ?? 'http://localhost:8000';

  return {
    envDir: projectRoot,
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
    server: {
      host: '0.0.0.0',
      port: 3000,
      // Dev через туннель (cloudflared/ngrok) к настоящему клиенту MAX: Vite режет
      // чужой Host, а адрес туннеля каждый раз новый.
      allowedHosts: true,
      // Bind-mount в Docker не всегда доставляет fs-события; compose включает polling.
      watch: { usePolling: process.env['CHOKIDAR_USEPOLLING'] === 'true' },
      proxy: { '^/api/': { target: proxyTarget, changeOrigin: true } },
    },
    build: { outDir: 'dist', sourcemap: true },
  };
});
