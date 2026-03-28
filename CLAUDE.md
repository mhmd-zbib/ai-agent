# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Update this file when you make architectural changes to the project.

---

## Quick Start

```bash
# Install all workspace packages
uv sync --dev

# Start infrastructure (postgres, redis, rabbitmq, minio, qdrant)
docker compose up -d

# Start FastAPI backend (port 8000)
uv run uvicorn api.main:app --reload

# Start RabbitMQ worker for document ingestion (Terminal 2)
uv run python -m pipeline.main

# Health check
curl http://localhost:8000/health

# Run all tests
uv run pytest -q

# Run with coverage
uv run pytest --cov=packages/api/src --cov=packages/pipeline/src --cov=packages/common/src --cov-fail-under=85 tests/

# Lint and format
uv run ruff check packages/
uv run ruff format packages/

# Type check (strict mode)
uv run mypy packages/common/src packages/api/src packages/pipeline/src --strict
```

---

## Architecture (Post-Migration: March 28, 2026)

The monorepo uses a `packages/` structure with three packages under a uv workspace.

### Directory Structure

```
agent-assitant/
├── packages/
│   ├── common/                  # Shared library (core, infra, agents, tools)
│   │   ├── pyproject.toml
│   │   └── src/common/
│   │       ├── core/            # Contracts layer (NO external drivers)
│   │       │   ├── config.py    # Settings, RagConfig, AgentConfig
│   │       │   ├── schemas.py   # Pydantic models (AIResponse, MemoryEntry, etc.)
│   │       │   ├── protocols.py # Abstract interfaces (IVectorClient, etc.)
│   │       │   ├── exceptions.py
│   │       │   ├── constants.py # Prompts, system messages
│   │       │   ├── log_config.py
│   │       │   ├── llm_utils.py
│   │       │   ├── utils.py
│   │       │   └── enums.py
│   │       ├── models/          # Domain models (agent.py, document.py, job.py)
│   │       ├── infra/           # Driver implementations
│   │       │   ├── db/          # postgres, redis, qdrant, pinecone, factory
│   │       │   ├── llm/         # base, openai, anthropic
│   │       │   ├── storage/     # minio
│   │       │   ├── messaging/   # rabbitmq
│   │       │   └── embedder.py
│   │       ├── agents/          # Agent library (importable, not a service)
│   │       │   ├── core/        # BaseAgent, AgentContext, AgentResult, MemoryAgent
│   │       │   ├── orchestrator/
│   │       │   ├── research/
│   │       │   ├── extraction/
│   │       │   ├── document/
│   │       │   └── runner.py
│   │       └── tools/           # Tool abstraction and registry
│   │           ├── base.py
│   │           ├── registry.py
│   │           ├── exceptions.py
│   │           ├── __init__.py  # get_tool_registry()
│   │           └── implementations/
│   │
│   ├── api/                     # FastAPI backend (HTTP layer)
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/api/
│   │       ├── main.py          # FastAPI app + composition root
│   │       ├── dependencies.py  # DI providers (get_current_user, require_admin, require_onboarding_complete)
│   │       ├── auth/            # JWT/crypto only — no DB (POST /v1/auth/login)
│   │       ├── users/           # User profiles + RBAC (register, me, admin list/role-update)
│   │       ├── admin/           # Academic ref-data CRUD (universities/faculties/majors/courses)
│   │       ├── onboarding/      # Student onboarding — uses admin IDs, not hardcoded enums
│   │       ├── chat/            # Chat endpoint (requires onboarding_complete)
│   │       ├── documents/       # Document upload (router, service, repository)
│   │       ├── memory/          # Short + long-term memory
│   │       ├── search/          # RAG service
│   │       └── health/          # Health check
│   │
│   └── pipeline/                # RabbitMQ worker (NO HTTP, pure consumer)
│       ├── pyproject.toml
│       ├── Dockerfile
│       └── src/pipeline/
│           ├── main.py          # Worker entry point
│           └── ingestion/       # 4-stage document ingestion pipeline
│               ├── service.py
│               ├── schemas.py
│               └── stages/      # parser, chunker, metadata, storage
│
├── docs/                        # Architecture docs
├── pyproject.toml               # Workspace root + tool config
└── CLAUDE.md
```

### Dependency Graph

```
common.core (contracts)
  ↓
common.infra (drivers) + common.tools (tool system)
  ↓
common.agents (reusable library)
  ↓
api (HTTP) + pipeline (worker)
```

**Rules:**
- ✅ `common.core` has NO external drivers (only Pydantic, structlog, PyJWT)
- ✅ `common.infra` depends on `common.core` only
- ✅ `common.tools` depends on `common.core` only
- ✅ `common.agents` depends on `common.core` + `common.infra` + `common.tools`
- ✅ `api` depends on `common` (all of core/infra/tools/agents)
- ✅ `pipeline` depends on `common` (core/infra only)
- ✅ `api` and `pipeline` are independent (can deploy separately)

### Import Namespaces

```python
# Core contracts
from common.core.config import Settings, AgentConfig, RagConfig
from common.core.schemas import AIResponse, AgentInput
from common.core.protocols import IVectorClient, IEmbeddingClient
from common.core.exceptions import AppError
from common.core.constants import ORCHESTRATOR_SYSTEM_PROMPT
from common.core.enums import University
from common.core.log_config import get_logger

# Domain models
from common.models.document import Document
from common.models.agent import AgentModel
from common.models.job import Job

# Infra drivers
from common.infra.db.postgres import create_postgres_engine
from common.infra.db.factory import create_vector_client
from common.infra.llm.openai import OpenAIClient
from common.infra.embedder import Embedder
from common.infra.storage.minio import MinioStorageClient
from common.infra.messaging.rabbitmq import RabbitMQPublisher

# Tools
from common.tools import get_tool_registry
from common.tools.base import BaseTool
from common.tools.registry import ToolRegistry

# Agents
from common.agents.orchestrator.agent import OrchestratorAgent
from common.agents.research.agent import ReasoningAgent, RetrievalAgent
from common.agents.core.context import AgentContext, AgentResult
from common.agents.core.memory import MemoryAgent

# API layer (was app.*)
from api.chat.service import ChatService
from api.auth.service import AuthService

# Pipeline layer (unchanged)
from pipeline.ingestion.service import ingest_document
```

---

## Common Tasks

### Adding a New Tool Implementation

1. Create `packages/common/src/common/tools/implementations/my_tool.py` with `MyTool(BaseTool)`
2. Register in `packages/common/src/common/tools/__init__.py` `get_tool_registry()`: `registry.register(MyTool())`
3. Export in `packages/common/src/common/tools/implementations/__init__.py`
4. Use in agent: `tool_registry.resolve("my_tool")`

### Adding a New Database Driver

1. Create `packages/common/src/common/infra/db/my_driver.py` implementing `IVectorClient`
2. Update `packages/common/src/common/infra/db/factory.py` to support new driver
3. Reference in `common.core.config.Settings` (e.g., `vector_backend = "my_driver"`)

### Running Tests for a Specific Layer

```bash
# Test just the api layer
uv run pytest tests/ -k "test_api" -v

# Test infra drivers
uv run pytest tests/ -k "test_infra" -v

# Test common/core contracts
uv run pytest tests/test_core/ -v
```

### Debugging Imports

```bash
# Check if module can be imported
uv run python -c "from api.chat.service import ChatService; print('OK')"
uv run python -c "from common.core.config import Settings; print('OK')"

# Find where a symbol comes from
uv run python -c "import api.chat.service; print(api.chat.service.__file__)"
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'core'"

**Cause:** Old import using `from core.*`
**Fix:** Replace with `from common.core.*`

### "ModuleNotFoundError: No module named 'infra'"

**Cause:** Old import using `from infra.*`
**Fix:** Replace with `from common.infra.*`

### "ModuleNotFoundError: No module named 'app'"

**Cause:** Old import using `from app.*`
**Fix:** Replace with `from api.*`

### Circular import error

**Cause:** Dependency graph violation (e.g., `common.core` importing from `common.infra`)
**Fix:** Check dependency direction: common.core → common.infra → common.agents → (api/pipeline)

### uv sync fails with dependency conflicts

**Cause:** Workspace members or sources misconfigured
**Fix:** Verify root `pyproject.toml` has:
```toml
[tool.uv.workspace]
members = ["packages/api", "packages/pipeline", "packages/common"]

[tool.uv.sources]
common = { workspace = true }
```

---

## Architecture Notes

**RAG Pipeline (Event-Driven):**

```
POST /v1/documents/upload
  → MinIO (presigned upload by client)
  → complete_upload() publishes DocumentUploadedEvent to RabbitMQ
     ↓
Stage 1 (parser):   download MinIO → parse PDF/DOCX/TXT
Stage 2 (chunker):  sliding-window chunker (512 tokens, 50 overlap)
Stage 3 (metadata): extract metadata via Anthropic API
Stage 4 (storage):  OpenAI embeddings → upsert to Pinecone/Qdrant
```

**FastAPI DI Pattern:**

Services are wired in `packages/api/src/api/main.py` and attached to `app.state`. Route handlers use `Depends(get_*)` — never instantiate services directly.

**LLM / Embedding Configuration:**

Point `OPENAI_BASE_URL` at Ollama or any OpenAI-compatible endpoint. Embedding is independent from chat LLM (use `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL`).

**Vector Backend:**

Switchable via `VECTOR_BACKEND=qdrant|pinecone`. Selected in `api/main.py` and injected into services via DI.

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
- All constants go in `packages/common/src/common/core/constants.py`. No hardcoded strings or values.
- Use `__all__` in every `__init__.py` to control public API.

---

## FastAPI Rules

- **Every route must have:** `summary`, `description`, `response_model`, and `status_code`.
- **Group routes by domain** using `APIRouter` with a prefix and tags. Never define routes in `main.py`.
- **Use dependency injection** for DB sessions, auth, AI clients, and config. Never instantiate these inside route handlers.
- **Never put business logic in route handlers.** Routes call services. Services call repositories.
- Always return typed Pydantic response schemas — never return raw dicts or ORM objects directly.

---

## AI / LLM Engineering Rules

- **All AI client logic lives in `common/infra/llm/`.** No SDK calls in routes or services directly.
- **Wrap every AI client in an abstract interface** (see `common/infra/llm/base.py`). Makes it mockable and swappable.
- **Always set timeouts** on AI API calls. Never let them hang indefinitely.
- **Log every AI request and response** with token counts, latency, and model name at DEBUG level.
- **Prompt templates are code.** Store them in `common/core/constants.py` — never hardcode prompts inline.

---

## Testing Rules

- **Every function, service, and route must have tests.**
- **Minimum coverage: 85%.** Run `pytest --cov=packages/.../src --cov-fail-under=85`.
- Tests must be **deterministic.** No random data, no time-dependent logic without mocking.
- Use **pytest** exclusively with **pytest-asyncio** (`asyncio_mode = "auto"`).
- Name tests: `test_<function>_<scenario>_<expected_outcome>`.
- No I/O in unit tests — mock everything external with `unittest.mock.AsyncMock` or `MagicMock`.
- **Never call real AI APIs, databases, or queues in tests.**

---

## Async Rules

- **The entire stack is async.** Use `async def` for all route handlers, services, and repository methods.
- Never use blocking I/O inside async functions — no `requests`, no synchronous file reads.
- Use `asyncio.gather` for concurrent independent operations.
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

- All custom exceptions inherit from `AppError` in `common/core/exceptions.py`.
- Register global exception handlers in `api/main.py` via `app.add_exception_handler`.
- Never expose internal stack traces or DB errors to API consumers.
- Always return errors in a consistent shape: `{ "error": { "code": "...", "message": "..." } }`.

---

## Logging

- Use **structured JSON logging** in production via `structlog` (configured in `common/core/log_config.py`).
- Log levels: `DEBUG` for AI calls and internals, `INFO` for requests, `WARNING` for recoverable errors, `ERROR` for failures.
- Every log entry must include: `request_id`, `service`, `timestamp`.

---

## Security

- Validate and sanitize all inputs using Pydantic — reject unknown fields with `model_config = ConfigDict(extra="forbid")`.
- Set strict CORS origins in production — never use `allow_origins=["*"]` outside local dev.

---

## Adding New Features

**New tool**: Subclass `BaseTool` in `packages/common/src/common/tools/implementations/`, implement `run()` and `to_openai_schema()`, register in `tools/__init__.py`.

**New API module**: Create `packages/api/src/api/<name>/` with `service.py`, `schemas.py`, `router.py`. Wire in `api/main.py`.

**New infrastructure driver**: Implement the relevant protocol from `common/core/protocols.py`, place in `common/infra/`, wire in `api/main.py`.

---

## CI Requirements

Every PR must pass:

```
uv run pytest --cov=packages/common/src --cov=packages/api/src --cov=packages/pipeline/src --cov-fail-under=85
uv run ruff check packages/
uv run ruff format --check packages/
uv run mypy packages/common/src packages/api/src --strict
```

---

## Code Style

- **Ruff** for linting and formatting. **mypy** in strict mode.
- Max line length: 100.
- Imports ordered: stdlib → third-party → local, separated by blank lines.
- No commented-out code in PRs.

---

## What Claude Should Never Do

- Never generate code without tests.
- Never put logic in route handlers — always delegate to a service.
- Never call AI APIs directly from outside `common/infra/llm/`.
- Never use `print()` — always use the structured logger.
- Never use `time.sleep()` in async code — use `asyncio.sleep()`.
- Never ignore a failing test to make CI pass.
- Never use mutable default arguments in function signatures.
