# ── Build stage ────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/prod.txt requirements.txt
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# ── Production stage ─────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update -y && \
    apt-get install -y --no-install-recommends libpq5 dumb-init && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*

COPY . .
RUN pip install -e .

RUN chown -R appuser:appuser /app
USER appuser

ENV PORT=8080

# Cloud Run sets $PORT; gunicorn with one uvicorn worker handles the simple
# synchronous processing this service does.
CMD ["sh", "-c", "gunicorn main:create_app --bind 0.0.0.0:$PORT --worker-class uvicorn.workers.UvicornWorker --workers 1 --threads 8 --timeout 120"]
