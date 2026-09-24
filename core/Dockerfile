# Образ сервиса core: один процесс api (HTTP, миграции при старте, воркер событий).
#
#   docker build --target runtime -t maxapp-core core     # прод (по умолчанию)
#   docker build --target test    -t maxapp-core-test core # прогон pytest внутри образа (deploy.sh)
#
# Зависимости ставит uv по uv.lock (--frozen: lock не пересчитывается); пакет
# core ставится editable из /app/src, поэтому dev-compose может подменить
# исходники bind-mount'ом без пересборки.
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml uv.lock ./

FROM base AS runtime
# LibreOffice без GUI — конвертер DOCX → PDF (core.files.pdf). Он тянет ~250 МБ
# пакетов и минуты сборки, поэтому включается флагом: локальный стенд должен
# собираться быстро (требование хакатона — не дольше 5 минут), а прод-образ
# собирается с WITH_PDF=true. Без него API отдаёт DOCX, а на PDF отвечает
# 503 render.pdf_unavailable. Шрифты DejaVu дают кириллицу, без них квадраты.
ARG WITH_PDF=false
RUN if [ "$WITH_PDF" = "true" ]; then \
      apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui fonts-dejavu \
      && rm -rf /var/lib/apt/lists/*; \
    fi
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY certs/ certs/
COPY src/ src/
RUN uv sync --frozen --no-dev
# Непривилегированный пользователь; каталог логов отдаём ему (bind-mount в проде).
RUN useradd --system --uid 10001 --create-home app \
    && mkdir -p /app/app_logs /app/app_data/documents \
    && chown -R app:app /app
USER app
# HEALTHCHECK задаётся в compose рядом с портами и таймингами сервиса.
CMD ["uvicorn", "core.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS test
RUN uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["python", "-m", "pytest", "tests", "-q", "--tb=short"]
