# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Update this file when you make architectural changes to the project.

---

## Commands

```bash
# Install dependencies
uv sync --dev

# Start infrastructure (postgres, redis, rabbitmq, minio, qdrant)
docker compose up -d

# Run API server with hot reload
uv run uvicorn api.main:app --app-dir packages/api --reload

# Run ingestion API server
uv run uvicorn ingestion.api.main:app --app-dir packages/ingestion --reload

# Run all tests (no infrastructure needed — everything is mocked)
uv run pytest -q

# Run a single test file
uv run pytest tests/test_chat.py -v

# Run a specific test
uv run pytest tests/test_chat.py::test_name -v

# Run with coverage
uv run pytest --cov=packages --cov-fail-under=85 tests/

# Lint and format
uv run ruff check packages/
uv run ruff format packages/

# Type check
uv run mypy packages/shared packages/api packages/ingestion
```

**Known pre-existing failures**:
- `tests/test_exceptions.py` — 2 tests about `x-request-id` header echoing.
- `tests/test_action_agent.py`, `tests/test_agent_service.py` — error message wording mismatches from staged `agent_service.py` changes.
- `tests/test_chat_service_tool_content.py` — fake `IMemoryService` missing `get_metadata`/`set_metadata` from staged `protocols.py` changes.

---

## Architecture

uv workspace monorepo with three installable packages:

```
packages/
├── shared/     — infra drivers + cross-cutting contracts
├── api/        — agent/chat FastAPI app
└── ingestion/  — 4-stage document ingestion pipeline + thin FastAPI wrapper
```

Dependency flow (still hexagonal):

```
api.modules/       → shared/           ← shared.infrastructure/
ingestion/         → shared/
(business)           (contracts)         (technology drivers)
```

No package imports from another package except `api → shared` and `ingestion → shared`. All wiring happens in `packages/api/api/main.py` (composition root for the chat API).

### Package → Python namespace mapping

| Package dir | Python import prefix |
|-------------|----------------------|
| `packages/shared/shared/` | `shared.*` |
| `packages/api/api/` | `api.*` |
| `packages/ingestion/ingestion/` | `ingestion.*` |
| `packages/agents/agents/` | `agents.*` |
| `packages/pipeline/pipeline/` | `pipeline.*` |

### Layer Responsibilities

| Layer | Path | Responsibility |
|-------|------|----------------|
| Modules | `packages/api/api/modules/` | Business logic only. No infrastructure imports. |
| Shared contracts | `packages/shared/shared/` | Protocols, schemas, config, logging, exceptions. |
| Ingestion pipeline | `packages/ingestion/ingestion/` | 4-stage document ingestion (parse → chunk → metadata → store). |
| Agents | `packages/agents/agents/` | Agent orchestration and execution. |
| Pipeline | `packages/pipeline/pipeline/` | Job pipeline processing. |

### Modules

- **`chat/`** — HTTP session flow: load memory → optional RAG → agent → persist memory.
- **`agent/`** — LLM orchestration: prompt → call LLM → if tool call, execute → re-call LLM.
- **`memory/`** — Dual-tier session storage: Redis (hot, TTL=3600s) + PostgreSQL (cold). Cache-aside + write-through.
- **`rag/`** — Retrieval: query vector DB → optional rerank → return context for chat.
- **`tools/`** — Plugin registry. Tools extend `BaseTool`, register in `packages/api/api/main.py`, and expose an OpenAI function schema.
- **`embeddings/`** — Redis-backed caching layer over the embeddings API.
- **`users/`** — JWT auth (HS256 via PyJWT + bcrypt passwords).

### RAG Pipeline (Event-Driven)

```
POST /v1/documents/upload
  → MinIO (presigned upload by client)
  → complete_upload() publishes DocumentUploadedEvent to documents.fanout exchange
     ↓
Stage 1 (parse_consumer):   download MinIO → parse PDF/DOCX/TXT → ParsedEvent
Stage 2 (chunk_consumer):   sliding-window chunker (512 tokens, 50 overlap) → ChunkEvent × N
Stage 3 (embed_consumer):   OpenAI embeddings API → EmbedEvent
Stage 4 (store_consumer):   upsert to Pinecone/Qdrant (namespace=user_id) → mark complete
```

Each queue has a paired DLQ via `x-dead-letter-exchange`. Workers run as daemon threads inside the FastAPI process.

### FastAPI DI Pattern

Services are wired in `app/main.py` and attached to `app.state`. `app/shared/deps.py` exposes typed `Depends()` accessors:

```python
def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service
```

Route handlers only call `Depends(get_*)` — never instantiate services directly.

### LLM / Embedding Configuration

The OpenAI SDK is used for all providers. Point `OPENAI_BASE_URL` at Ollama or any OpenAI-compatible endpoint. Embedding model configuration is independent from chat LLM (use `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`), enabling mixed providers (e.g., Ollama for chat + OpenAI for embeddings).

### Vector Backend

Switchable via `VECTOR_BACKEND=qdrant|pinecone`. Backend is selected in `app/main.py` and injected into `StoreService` and `VectorRepository`. Both implement the same `IVectorClient` protocol from `app/infrastructure/vector/base.py`.

---

## Core Principles

- **Every feature needs a test.** No code is considered done without tests covering it.
- **Explicit over implicit.** Never rely on magic or hidden behavior.
- **Fail loudly.** Raise clear errors. Never swallow exceptions silently.
- **Keep it small.** Functions do one thing. Files stay focused. Modules stay cohesive.
- **AI calls are side effects.** Treat LLM/model calls like DB or network calls — isolated, injectable, testable.

---

## Python Standards

- **Python version:** 3.12+
- **Type hints are mandatory** on every function signature — parameters and return types.
- **Pydantic v2** for all data validation and serialization.
- **No `Any` type** unless absolutely unavoidable and explicitly justified with a comment.
- Use `|` union syntax — write `str | None`, not `Optional[str]`.
- All constants go in `app/shared/config.py` via `pydantic-settings`. No hardcoded strings or values.
- Use `__all__` in every `__init__.py` to control public API.

---

## FastAPI Rules

- **Every route must have:** `summary`, `description`, `response_model`, and `status_code`.
- **Group routes by domain** using `APIRouter` with a prefix and tags. Never define routes in `main.py`.
- **Use dependency injection** for DB sessions, auth, AI clients, and config. Never instantiate these inside route handlers.
- **Never put business logic in route handlers.** Routes call services. Services call repositories.
- Always return typed Pydantic response schemas — never return raw dicts or ORM objects directly.
- Use `HTTPException` with clear `detail` messages. Define custom exception handlers in `app/shared/exceptions.py`.

```python
@router.post(
    "/completions",
    summary="Generate a completion",
    description="Sends a prompt to the configured LLM and returns the response.",
    response_model=CompletionResponse,
    status_code=status.HTTP_200_OK,
)
async def create_completion(
    payload: CompletionRequest,
    service: CompletionService = Depends(get_completion_service),
) -> CompletionResponse:
    return await service.complete(payload)
```

---

## AI / LLM Engineering Rules

- **All AI client logic lives in `app/infrastructure/llm/` or `app/infrastructure/embedding/`.** No SDK calls in modules or routes.
- **Wrap every AI client in an abstract interface** (see `app/shared/llm/base.py`). Makes it mockable and swappable.
- **Always set timeouts** on AI API calls. Never let them hang indefinitely.
- **Log every AI request and response** with token counts, latency, and model name at DEBUG level.
- **Handle AI-specific errors explicitly:** rate limits, context length exceeded, model unavailable.
- **Prompt templates are code.** Store them in `app/shared/constants.py` or versioned files — never hardcode prompts inline.
- Implement retry logic with exponential backoff for transient AI API failures using `tenacity`.

---

## Testing Rules

- **Every function, service, and route must have tests.**
- **Test file mirrors source file:** `app/modules/chat/services/chat_service.py` → `tests/test_chat_service.py`
- **Minimum coverage: 85%.** Run `pytest --cov=app --cov-fail-under=85`.
- Tests must be **deterministic.** No random data, no time-dependent logic without mocking.
- Use **pytest** exclusively with **pytest-asyncio** (`asyncio_mode = "auto"`).
- Name tests: `test_<function>_<scenario>_<expected_outcome>`.
- No I/O in unit tests — mock everything external with `unittest.mock.AsyncMock` or `MagicMock`.
- Use `pytest.mark.parametrize` for multiple input variants.
- **Never call real AI APIs, databases, or queues in tests.**
- For integration tests, use **testcontainers** for real PostgreSQL/Redis. Mock external AI APIs via `respx` or `pytest-httpx`.
- For E2E tests, use FastAPI's `AsyncClient` from `httpx`.

---

## Async Rules

- **The entire stack is async.** Use `async def` for all route handlers, services, and repository methods.
- Never use blocking I/O inside async functions — no `requests`, no synchronous file reads.
- Use `asyncio.gather` for concurrent independent operations.
- Use `anyio.to_thread.run_sync` to wrap unavoidably blocking calls.
- DB sessions must use `AsyncSession` from `sqlalchemy.ext.asyncio`.

---

## Database Rules

- **SQLAlchemy 2.0+** with async engine only.
- All schema changes go through **Alembic migrations.** Never use `create_all()` in production.
- **Repository pattern is mandatory.** No ORM queries outside `repositories/`.
- Always use `select()` with explicit columns — never `SELECT *`.
- Paginate every list endpoint. Default page size: 20. Max: 100.

---

## Error Handling

- All custom exceptions inherit from `AppException` in `app/shared/exceptions.py`.
- Register global exception handlers in `app/main.py` via `app.add_exception_handler`.
- Never expose internal stack traces or DB errors to API consumers.
- Always return errors in a consistent shape: `{ "error": { "code": "...", "message": "..." } }`.

---

## Logging

- Use **structured JSON logging** in production via `structlog` (configured in `app/shared/logging.py`).
- Log levels: `DEBUG` for AI calls and internals, `INFO` for requests, `WARNING` for recoverable errors, `ERROR` for failures.
- Every log entry must include: `request_id`, `service`, `timestamp`.

---

## Security

- Validate and sanitize all inputs using Pydantic — reject unknown fields with `model_config = ConfigDict(extra="forbid")`.
- Set strict CORS origins in production — never use `allow_origins=["*"]` outside local dev.

---

## Adding New Features

**New tool**: Subclass `BaseTool` in `app/modules/tools/implementations/`, implement `run()` and `to_openai_schema()`, register in `app/main.py`.

**New module**: Create `app/modules/<name>/` with `services/`, `schemas/`, optionally `router.py`. Wire in `app/main.py`. Define cross-module protocols in `app/shared/protocols.py`, not in the module itself.

**New infrastructure driver**: Implement the relevant protocol from `app/infrastructure/*/base.py`, wire in `app/main.py`.

---

## CI Requirements

Every PR must pass:

```
uv run pytest --cov=app --cov-fail-under=85
uv run ruff check .
uv run ruff format --check .
uv run mypy app/
```

---

## Code Style

- **Ruff** for linting and formatting. **mypy** in strict mode.
- Max line length: 100.
- Imports ordered: stdlib → third-party → local, separated by blank lines.
- No commented-out code in PRs.

```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
python_version = "3.11"

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
```

---

## What Claude Should Never Do

- Never generate code without tests.
- Never put logic in route handlers — always delegate to a service.
- Never call AI APIs directly from outside `app/infrastructure/llm/` or `app/infrastructure/embedding/`.
- Never use `print()` — always use the structured logger.
- Never use `time.sleep()` in async code — use `asyncio.sleep()`.
- Never ignore a failing test to make CI pass.
- Never use mutable default arguments in function signatures.
