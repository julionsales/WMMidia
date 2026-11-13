# syntax=docker/dockerfile:1.7
# Imagem única com dois alvos:
#   app    -> API, scheduler e tarefas administrativas (sem navegador)
#   worker -> app + Playwright/Chromium e dependências do sistema
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /srv
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --home /home/app --create-home app
COPY requirements.txt requirements.lock* ./
RUN if [ -f requirements.lock ]; then pip install -r requirements.lock; else pip install -r requirements.txt; fi

FROM base AS app
COPY app ./app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--timeout-graceful-shutdown", "20"]

FROM base AS worker
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY requirements-worker.txt ./
RUN pip install -r requirements-worker.txt \
    && playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && chmod -R a+rX /ms-playwright
COPY app ./app
USER app
CMD ["celery", "-A", "app.worker.celery_app:celery_app", "worker", "--loglevel=INFO", "-Q", "inventory,instagram,default", "--concurrency=2"]

FROM base AS test
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY app ./app
COPY tests ./tests
COPY pytest.ini ./
CMD ["pytest", "-q"]
