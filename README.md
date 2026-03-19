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
- Docker (for PostgreSQL + Redis via `compose.yaml`)
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
```

Runtime behavior: reads chat history from Redis first; on cache miss, loads from PostgreSQL and rehydrates Redis.

## Infrastructure setup (Docker Compose)

Start PostgreSQL and Redis:

```bash
docker compose up -d postgres redis
```

Check health:

```bash
docker compose ps
```

Stop services:

```bash
docker compose down
```

Data is persisted in named Docker volumes `postgres_data` and `redis_data`.

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
- `POST /v1/agent/chat`
- `DELETE /v1/agent/sessions/{session_id}`

### Sample chat request

```json
{
  "message": "Help me design a clean FastAPI architecture.",
  "session_id": "optional-session-id"
}
```

## Tests

```bash
uv run pytest -q
```

Tests use fake in-test repositories/services and do not require external infra.
