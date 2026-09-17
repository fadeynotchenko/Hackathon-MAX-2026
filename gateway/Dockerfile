# Образ gateway: собирает мини-апп (web/) и отдаёт его статикой + проксирует /api/ и вебхук бота.
# В прод уезжает только dist/ поверх nginx:alpine; Node в финальном образе нет.
FROM node:24-alpine AS web-build
WORKDIR /repo
RUN npm install -g pnpm@12.4.2 --silent
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml tsconfig.base.json tsconfig.json ./
COPY web/package.json web/
COPY bot/package.json bot/
RUN pnpm install --frozen-lockfile --filter @maxapp/web...
COPY web/ web/
# База API для бандла. Пусто ⇒ same-origin (/api/v1 через этот же nginx).
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN pnpm --filter @maxapp/web build

FROM nginx:1.27-alpine
# Шаблон рендерится штатным entrypoint'ом образа: ${DOMAIN} и прочие
# переменные подставляются envsubst при старте контейнера, а не на сборке.
COPY gateway/templates/ /etc/nginx/templates/
COPY gateway/snippets/ /etc/nginx/snippets/
COPY --from=web-build /repo/web/dist /usr/share/nginx/html
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1/nginx-health >/dev/null || exit 1
