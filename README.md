# Agent Assistant Platform

A production-grade AI conversational agent platform built on FastAPI. Supports tool-augmented conversations, persistent multi-tier memory, and event-driven document ingestion — organized around strict clean architecture boundaries.

---

## What Was Built

A backend system where users authenticate, open chat sessions, send messages to an AI agent, and upload documents for knowledge augmentation. The agent can autonomously decide to invoke registered tools mid-conversation, synthesize the results, and continue the dialogue — all while maintaining full session memory across requests.

Key capabilities:
- Multi-turn conversations with full history context
- Autonomous tool selection and execution by the LLM
- Two-tier session memory (Redis cache + PostgreSQL persistence)
- Async document ingestion via object storage + message queue
- JWT-authenticated, multi-user, session-isolated by design

---

## Architecture

The codebase follows **hexagonal architecture** — business logic never depends on infrastructure. Dependencies only flow inward toward the domain.

```
┌──────────────────────────────────────────────────────┐
│                     main.py                           │
│              Composition root only.                   │
│         Wires all layers together at startup.         │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│                 app/modules/                          │
│  Business logic. Imports from shared/ only.           │
│  Modules never import each other directly.            │
│  chat · agent · memory · documents · users · tools    │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│              app/infrastructure/                      │
│  Concrete technology drivers. Imports shared/ only.   │
│  database · messaging · storage · llm                 │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│                 app/shared/                           │
│  Contracts and domain types. Zero module imports.     │
│  schemas · protocols · llm/base · config · logging    │
└──────────────────────────────────────────────────────┘
```

This structure was a deliberate choice rather than a simpler flat layout. The constraint it enforces — that no module can call another module's code directly — eliminates an entire class of coupling problems as the system grows.

---

## Design Decisions

### Dependency Inversion via Protocols

Modules depend on abstract interfaces (`typing.Protocol`) defined in `shared/protocols.py`, never on concrete implementations. `ChatService`, for example, knows nothing about Redis, PostgreSQL, or the OpenAI SDK:

```
ChatService
  ├── BaseLLM (abstract)         ← infrastructure/llm/openai.py implements this
  ├── IMemoryService (protocol)  ← memory/services/memory_service.py implements this
  └── IToolRegistry (protocol)   ← tools/registry.py implements this
```

`main.py` is the only place where abstractions are bound to implementations. This means every service is testable in complete isolation — swap in a fake `IMemoryService`, pass it to `ChatService`, no infrastructure needed.

---

### Memory: Two-Tier Cache-Aside + Write-Through

Every message turn requires reading the full session history. Loading from PostgreSQL on every request adds 100–200ms per turn. The memory layer solves this with a dual-tier strategy:

```
Read  → Redis first (~1ms) → miss → PostgreSQL (~100ms) → repopulate Redis
Write → PostgreSQL (authoritative) → update Redis (keep hot)
```

`MemoryService` owns this logic entirely. Neither the caller nor the repositories know which tier served the data. Redis holds up to 1000 active sessions (LRU eviction) with TTL-based expiry. PostgreSQL is the source of truth — Redis can be wiped without data loss.

---

### Tool Execution: Plugin Registry

Tools are plugins. Adding a new tool requires no changes to existing code — define a `BaseTool` subclass, register it once in `main.py`, and the LLM can immediately use it.

The LLM is given all registered tool schemas on every call. It decides autonomously whether to invoke a tool based on the user's intent. When it does, `ToolExecutor` resolves the tool name from `IToolRegistry`, calls `tool.run(arguments)`, and injects the result back into the conversation for the LLM to synthesize a final answer.

```
User message
    │
    ▼
LLM sees tool schemas → decides to call "weather_lookup"
    │
    ▼
ToolExecutor → registry.resolve("weather_lookup") → tool.run({"city": "NYC"})
    │
    ▼
Result injected → LLM synthesizes final answer
```

---

### Document Ingestion: Decoupled by Events

Large file uploads can't be processed synchronously — processing time is unpredictable and unrelated to the HTTP response. The upload endpoint does exactly two things: store the file in object storage, emit an event. Everything else is async.

```
POST /v1/documents/uploads
  ├── Chunk file → upload to MinIO
  ├── Publish event → RabbitMQ
  └── Return upload_id  (< 100ms regardless of file size)

                 ↓ async

document_uploaded_consumer
  ├── Reads from queue
  ├── Fetches chunks from MinIO
  └── Processes: embeddings, indexing, metadata
```

`DocumentService` depends on two repository protocols (`IDocumentStorageRepository`, `IDocumentEventRepository`) — it never calls MinIO or RabbitMQ directly. Workers can be scaled horizontally without touching the API. If a worker crashes, RabbitMQ re-queues the message automatically.

---

## Full Request Lifecycle

What happens when a user sends a message:

```
POST /v1/agent/chat { session_id, message }
        │
        ▼
1.  JWT verification → extract user_id
        │
        ▼
2.  MemoryService.get_session_state(session_id)
    ├── Redis hit  → return in ~1ms
    └── Redis miss → PostgreSQL → repopulate Redis → return
        │
        ▼
3.  PromptBuilder constructs system prompt with tool schemas
        │
        ▼
4.  LLM called with full history + tool definitions
        │
    ┌───┴──────────────────────┐
    │ LLM returns tool_call    │ LLM answers directly
    ▼                          ▼
5.  ToolExecutor.run(calls)    skip to step 7
    resolve → run → result
        │
        ▼
6.  LLM re-called with tool result → synthesizes final answer
        │
        ▼ (paths rejoin)
7.  MemoryService.append_message → PostgreSQL + Redis
        │
        ▼
8.  HTTP response { type, content, metadata }
```

---

## Stack

| Concern | Technology | Why |
|---------|-----------|-----|
| API | FastAPI + Pydantic | Async-native, type-safe, auto-generated docs |
| LLM | OpenAI SDK | Native function calling; `base_url` override enables Ollama/Azure without code changes |
| Hot memory | Redis 7 | Sub-millisecond session reads |
| Persistent storage | PostgreSQL 16 | ACID message history; pgvector ready for RAG |
| Document storage | MinIO | S3-compatible, self-hosted, swappable with AWS S3 |
| Event queue | RabbitMQ 3.13 | Durable delivery, dead-letter queues for failed processing |
| Auth | JWT + bcrypt | Stateless; no server-side session state |
| Config | pydantic-settings | Type-safe env parsing, validated at startup |

---

## Running Locally

```bash
cp .env.example .env   # add OPENAI_API_KEY
uv sync --dev
docker compose up -d
uv run uvicorn main:app --reload
# → http://localhost:8000/docs
```

To run the document consumer:
```bash
uv run python -m app.workers.document_uploaded_consumer
```

Tests run without any infrastructure (all external dependencies are faked):
```bash
uv run pytest -q
```
