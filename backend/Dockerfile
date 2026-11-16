# syntax=docker/dockerfile:1
# SmartPOS AI backend (FastAPI). Build: docker build -t smartpos-backend ./backend

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS deps
COPY requirements.txt .
# Behind a TLS-intercepting proxy, pass its CA bundle as a build secret (never stored in a layer):
#   docker build --secret id=extra_ca,src=/path/to/ca-bundle.pem ./backend
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi; \
    pip install --prefix=/install -r requirements.txt

FROM base AS runtime
RUN groupadd --system app && useradd --system --gid app --home-dir /app --no-create-home app
COPY --from=deps /install /usr/local
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh
USER app

# Only trust X-Forwarded-For from these addresses (used for login rate limiting).
# docker-compose sets "*" because the backend is reachable only through the frontend.
ENV APP_ENV=production \
    LOG_FORMAT=json \
    FORWARDED_ALLOW_IPS=127.0.0.1 \
    PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/api/v1/health\", timeout=4)"]
ENTRYPOINT ["docker-entrypoint.sh"]
# One worker: the login and assistant rate limiters keep their counters in process memory.
# Worker count: WEB_CONCURRENCY (Uvicorn's standard variable, default 1). Rate limits and
# live updates are stored in PostgreSQL, so several workers share them correctly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
