FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY gateway ./gateway
# Do not bake .env; provide via env_file / -e at runtime.
COPY .env.example ./.env.example

RUN mkdir -p /app/data

ENV APP_ENV=prod DEBUG=false HOST=0.0.0.0 PORT=8080
EXPOSE 8080

# Single worker: in-memory rate limiter is per-process.
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
