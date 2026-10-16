# ============================================
# Dexter Retrieval Engine - ingestion worker image
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
 && apt-get update && apt-get install -y --no-install-recommends curl poppler-utils && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY backend/ .
RUN mkdir -p /app/uploads /app/data && chown -R appuser:appgroup /app
USER appuser
CMD ["python", "-m", "src.ingestion.worker"]
