# -------------------------------------------------------------
# 🧱 Stage 1: Builder — install dependencies separately for speed
# -------------------------------------------------------------
FROM python:3.12-slim AS builder

# Prevent Python from writing pyc files / buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build essentials for numpy, motor, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy source code
COPY . .

# -------------------------------------------------------------
# 🚀 Stage 2: Runner — lightweight final image
# -------------------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# ✅ this must match where your app/main.py lives
WORKDIR /app/app

# Copy only built dependencies and app code
COPY --from=builder /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Expose Cloud Run port
EXPOSE 8080

# Optional healthcheck
HEALTHCHECK CMD curl --fail http://localhost:8080/health || exit 1

# ✅ Corrected entry point (important)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
