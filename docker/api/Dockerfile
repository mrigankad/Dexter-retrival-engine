# ============================================
# Dexter Retrieval Engine - API image
# ============================================
FROM python:3.12-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements-optional.txt ./
ARG INSTALL_OPTIONAL=false
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$INSTALL_OPTIONAL" = "true" ]; then pip install --no-cache-dir -r requirements-optional.txt; fi

FROM python:3.12-slim AS production
WORKDIR /app
RUN groupadd -r appgroup && useradd -r -g appgroup appuser \
 && apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY backend/ .
COPY evals/ ./evals/
RUN mkdir -p /app/uploads /app/data && chown -R appuser:appgroup /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD curl -f http://localhost:8000/health/live || exit 1
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8000", "--workers", "2", \
     "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "180", "--keep-alive", "5", \
     "--access-logfile", "-", "--error-logfile", "-"]
