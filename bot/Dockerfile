# Образ бота (Node). Собирается из корня репозитория: pnpm-lock общий на воркспейсы.
#   docker build -f bot/Dockerfile -t maxapp-bot .
FROM node:24-alpine AS build
WORKDIR /repo
RUN npm install -g pnpm@12.4.2 --silent
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml tsconfig.base.json tsconfig.json ./
COPY bot/package.json bot/
COPY web/package.json web/
RUN pnpm install --frozen-lockfile --filter @maxapp/bot...
COPY bot/ bot/
RUN pnpm --filter @maxapp/bot build \
    && pnpm --filter @maxapp/bot --prod deploy --legacy /out

FROM node:24-alpine
ENV NODE_ENV=production
# Bot API MAX работает под корнем Минцифры, которого нет в хранилище Node
# (см. bot/certs/README.md): без него любой запрос к platform-api2.max.ru падает.
COPY bot/certs/russian_trusted_root_ca.pem /etc/ssl/certs/russian_trusted_root_ca.pem
ENV NODE_EXTRA_CA_CERTS=/etc/ssl/certs/russian_trusted_root_ca.pem
WORKDIR /app
COPY --from=build /out/node_modules ./node_modules
COPY --from=build /out/package.json ./package.json
COPY --from=build /repo/bot/dist ./dist
RUN mkdir -p /app/app_logs && chown -R node:node /app
USER node
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -qO- "http://127.0.0.1:${BOT_HEALTH_PORT:-8081}/health" >/dev/null || exit 1
CMD ["node", "dist/main.js"]
