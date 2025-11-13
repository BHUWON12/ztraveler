# -------------------------------------------------------------
# 🏗️ Stage 1: Builder
# -------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source code
COPY . .

# -------------------------------------------------------------
# 🚀 Stage 2: Runtime (Slim & Cloud Run Ready)
# -------------------------------------------------------------
FROM python:3.12-slim

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Copy dependencies & app
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Healthcheck (Cloud Run probes this)
HEALTHCHECK --interval=30s --timeout=5s \
  CMD curl -f http://localhost:${PORT}/health || exit 1

# Expose the FastAPI port
EXPOSE 8080

# ✅ Launch FastAPI (non-blocking)
CMD ["bash", "-c", "echo '🚀 Starting FastAPI on port ${PORT}...' && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
