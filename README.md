# Agent Assistant (FastAPI + OpenAI)

FastAPI server with Redis-first memory, PostgreSQL persistence, and modular feature folders.

## Architecture

- `app/main.py`: app composition and startup wiring
- `app/modules/chat`: chat HTTP + orchestration
- `app/modules/agent`: agent loop + LLM clients + tool execution
- `app/modules/memory`: Redis short-term + Postgres long-term memory
- `app/modules/rag`: scaffolded RAG services/repositories/embedders
- `app/modules/tools`: tool registry + implementations
- `app/modules/users`: scaffolded user/auth modules
- `app/shared`: infrastructure only (config, deps, exceptions, db, middleware, base)

## Requirements

- Python 3.12+
- Docker (for PostgreSQL + Redis + RabbitMQ + MinIO via `compose.yaml`)
- `OPENAI_API_KEY`

## Environment setup

Copy the example and update values:

```bash
cp .env.example .env
```

Required persistence settings:

```env
DATABASE_URL=postgresql+psycopg://agent_user:agent_password@localhost:5432/agent_assistant
REDIS_URL=redis://localhost:6379/0
REDIS_CHAT_CACHE_TTL_SECONDS=3600
RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=documents
DOCUMENT_CHUNK_SIZE_BYTES=1048576
```

Runtime behavior: reads chat history from Redis first; on cache miss, loads from PostgreSQL and rehydrates Redis.

## Infrastructure setup (Docker Compose)

Start PostgreSQL, Redis, RabbitMQ, and MinIO:

```bash
docker compose up -d postgres redis rabbitmq minio
```

Check health:

```bash
docker compose ps
```

Stop services:

```bash
docker compose down
```

Data is persisted in named Docker volumes `postgres_data`, `redis_data`, and `minio_data`.

## Run the API

Install dependencies:

```bash
uv sync --dev
```

Run server:

```bash
uv run uvicorn main:app --reload
```

Server runs at `http://127.0.0.1:8000`.

## Main Endpoints

- `GET /health`
- `POST /v1/users/register`
- `POST /v1/users/login`
- `POST /v1/agent/sessions` (create chat session)
- `POST /v1/agent/chat` (send only new turn)
- `DELETE /v1/agent/sessions/{session_id}`
- `POST /v1/documents/uploads` (multipart upload, chunk + publish event)

## Document upload + event flow

1. Client uploads a file to `POST /v1/documents/uploads` (`multipart/form-data`).
2. API chunks the file (`DOCUMENT_CHUNK_SIZE_BYTES`) and stores chunks + manifest in MinIO.
3. API publishes `document.uploaded` to RabbitMQ.
4. Consumer reads events and logs processing metadata.

Run the consumer worker:

```bash
uv run python -m app.workers.document_uploaded_consumer
```

## Tests

```bash
uv run pytest -q
```

Tests use fake in-test repositories/services and do not require external infra.
