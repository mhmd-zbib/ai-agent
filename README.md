# Agent Assistant Platform

A production-grade **AI-powered conversational agent platform** built on FastAPI, OpenAI, and enterprise-scale cloud infrastructure. Enables teams to build, deploy, and scale intelligent agents that can leverage tools, maintain conversation memory across sessions, and process large document uploads for knowledge-augmented responses.

---

## Business Value & Use Cases

### What Problem Does It Solve?

Organizations need intelligent systems that can:

1. **Engage in Natural Conversations** — Users interact with an AI agent as they would with a human, with full conversation context preserved across sessions
2. **Execute Tools Intelligently** — The AI agent can autonomously decide when to use specific tools/APIs to fulfill requests (calculators, web search, document lookup, etc.)
3. **Remember Context Over Time** — Sessions persist across interactions, allowing the agent to recall previous messages and build on them
4. **Ingest and Analyze Documents** — Teams can upload large files and have the agent intelligently summarize, extract, or search across them
5. **Scale Securely** — Multi-user access with authentication, audit trails, and production-ready monitoring

### Real-World Applications

- **Customer Support Automation** — AI agent handles FAQs, routes to humans, and maintains ticket context
- **Knowledge Worker Assistant** — Engineers/analysts upload docs, ask questions, get intelligent summaries
- **Internal Chatbot** — HR/IT automation for onboarding, policy lookup, IT troubleshooting
- **Sales Assistant** — Analyze customer data, recall deals, draft responses with tool-powered insights
- **Research Assistant** — Ingest papers/reports, answer queries across multiple documents

---

## System Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────┐
│                    Client Applications                       │
│  (Web, Mobile, Desktop, Third-party integrations)           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ HTTPS
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              FastAPI Application Server (app/main.py)       │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Auth & Session Management (app/modules/users)        │ │
│  │  ✓ JWT token-based authentication                     │ │
│  │  ✓ Role-based access control                          │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Chat & Agent Orchestration (app/modules/chat)        │ │
│  │  • Session management (create/reset)                  │ │
│  │  • User message → AI response pipeline                │ │
│  │  • Tool execution coordination                        │ │
│  │  • Response serialization & caching                  │ │
│  └────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Document Ingestion (app/modules/documents)           │ │
│  │  • Multipart file upload handling                     │ │
│  │  • Server-side chunking (configurable size)           │ │
│  │  • Event publishing to message queue                  │ │
│  └────────────────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────────────────┘
                 │
   ┌─────────────┼──────────────┬──────────────┐
   │             │              │              │
   ▼             ▼              ▼              ▼
┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────────┐
│ Redis    │ │PostgreSQL│ │RabbitMQ  │ │MinIO Storage │
│ (Cache)  │ │(Persist)│ │(Events)  │ │(Documents)  │
└──────────┘ └────────┘ └──────────┘ └──────────────┘
   LRU        Long-term  Event Stream    File Bucket
  Cache      Memory      (Async)        (Scalable)
```

### Layered Architecture

The codebase follows **layered architecture** principles with clear separation of concerns:

#### Layer 1: HTTP API (Routers)
- `app/modules/chat/router.py` — Chat endpoints
- `app/modules/users/router.py` — Auth endpoints
- `app/modules/documents/router.py` — Upload endpoints

**Responsibility:** Request/response serialization, auth guards, OpenAPI schema

#### Layer 2: Services (Business Logic)
- `app/modules/chat/services/chat_service.py` — Chat orchestration
- `app/modules/users/services/user_service.py` — User management
- `app/modules/documents/services/document_service.py` — Document ingestion
- `app/modules/memory/services/memory_service.py` — Memory management

**Responsibility:** Workflow coordination, tool invocation, state management, error handling

#### Layer 3: Domain Models & Repositories
- `app/modules/memory/repositories/` — Redis/PostgreSQL storage
- `app/modules/tools/` — Tool registry & implementations
- `app/modules/agent/` — LLM client wrappers

**Responsibility:** Data persistence, schema enforcement, persistence strategy abstraction

#### Layer 4: Infrastructure (Shared)
- `app/shared/storage/` — MinIO client
- `app/shared/messaging/` — RabbitMQ client
- `app/shared/db/` — Database drivers
- `app/shared/config.py` — Environment configuration
- `app/shared/exceptions.py` — Error handling
- `app/shared/logging.py` — Observability

**Responsibility:** External service integration, configuration, cross-cutting concerns

---

## Core Design Patterns

### 1. **Memory Management: Cache-Aside Pattern**

**Problem:** Conversational AI requires instant access to message history, but loading from PostgreSQL on every turn adds 100-200ms latency.

**Solution:** Hybrid memory architecture with cache-aside pattern:

```python
# Flow: Check Redis first → Fallback to PostgreSQL → Update Redis
def get_session_state(session_id: str) -> SessionState:
    # 1. Fast path: Check hot cache (Redis)
    if cached := short_term_repository.get_messages(session_id):
        return SessionState(session_id, cached)  # ✓ ~1ms
    
    # 2. Slow path: Load from persistent store
    messages = long_term_repository.get_messages(session_id)  # ~50-200ms
    
    # 3. Repopulate cache for next access
    short_term_repository.set_messages(session_id, messages)
    return SessionState(session_id, messages)
```

**Benefits:**
- Frequently-accessed sessions have ~1ms response time
- Automatic cache invalidation (TTL-based)
- LRU eviction prevents memory bloat (tracks 1000 active sessions)
- No explicit cache invalidation required (simpler operations)

---

### 2. **Tool Execution: Plugin Architecture**

**Problem:** Hard-coding tools creates tight coupling and makes the system difficult to extend. Customers need to add custom tools (internal APIs, domain-specific functions).

**Solution:** Plugin pattern with protocol-based discovery:

```python
# Tool registry acts as service locator
class ToolRegistry(IToolRegistry):
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None:
        # Register tool once on startup
        self._tools[tool.name] = tool
    
    def resolve(self, tool_name: str) -> BaseTool:
        # LLM invokes by name; system resolves to implementation
        return self._tools[tool_name]  # Raises KeyError if missing
    
    def get_tools_for_openai(self) -> list[dict]:
        # Convert all tools to OpenAI function calling format
        return [tool.to_openai_tool() for tool in self._tools.values()]
```

**How the LLM Uses Tools:**
1. LLM sees tool definitions (schema, parameters)
2. When user query matches tool purpose, LLM decides to invoke it
3. LLM structures response: `{"tool_name": "calculator", "arguments": {"expression": "15 + 20"}}`
4. Executor resolves tool by name and calls `tool.run(arguments)`
5. Result is returned to LLM for final answer composition

**Benefits:**
- New tools = one new class + `register()` call
- LLM makes autonomous decisions about when to use tools
- Extensible to OpenAI-compatible models (Anthropic, local LLMs, etc.)

---

### 3. **Document Ingestion: Event-Driven Pipeline**

**Problem:** Large file uploads can timeout. Processing needs to happen asynchronously without blocking the API response.

**Solution:** Chunked upload + event-driven worker pattern:

```
User Upload Request
    ↓
1. Server chunks file (1MB chunks default)
    ↓
2. Store chunks + metadata in MinIO (scalable object store)
    ↓
3. Publish "document.uploaded" event to RabbitMQ
    ↓
4. Return immediately (user gets upload_id)
    ↓
    ├─→ Consumer Worker 1: Process document metadata
    ├─→ Consumer Worker 2: Generate embeddings
    └─→ Consumer Worker 3: Index for RAG search
```

**Code example:**
```python
# Upload endpoint (synchronous, fast)
@router.post("/documents/uploads")
async def upload_document(file: UploadFile, ...):
    response = service.upload_chunked_document(
        file=file,
        user_id=current_user.id,
        chunk_size_bytes=1024 * 1024  # 1MB chunks
    )
    # Returns immediately, processing happens asynchronously
    return response

# Consumer worker (separate process)
def consume_forever():
    connection = pika.BlockingConnection(...)
    channel = connection.channel()
    
    def on_message(channel, method, properties, body):
        event = json.loads(body)
        # Process: update indexes, generate embeddings, etc.
        logger.info(f"Processed {event['upload_id']}")
        channel.basic_ack(method.delivery_tag)
    
    channel.basic_consume(queue="documents.uploaded.queue", on_message_callback=on_message)
    channel.start_consuming()
```

**Benefits:**
- API response is sub-100ms regardless of file size
- Horizontal scaling: add more workers for more throughput
- Resilience: if worker crashes, RabbitMQ holds messages until reprocessing
- Observability: event logs show exact processing timeline

---

### 4. **Session Isolation: Multi-Tenant by Design**

**Problem:** Different users' conversations must be completely isolated (privacy, security, billing).

**Solution:** Session-keyed data model with per-user auth:

```python
# Every operation is keyed to (user_id, session_id)
@router.post("/v1/agent/chat")
async def chat(
    payload: ChatRequest,  # Contains session_id
    current_user = Depends(get_current_user),  # Auth guard
):
    # Session must belong to current_user (enforced in service)
    state = memory_service.get_session_state(payload.session_id)
    # Messages for this session are separate from other users
```

**Benefits:**
- User A cannot access User B's conversations
- Audit trail: every message linked to user + timestamp
- Cost attribution: usage counted per session
- GDPR/privacy: delete user → delete all sessions atomically

---

## Data Flow: Complete Chat Turn

Here's what happens when a user sends a message:

```
1. HTTP Request
   POST /v1/agent/chat
   {
     "session_id": "sess-abc123",
     "message": "What's the weather in NYC?"
   }

2. Authentication
   └─ Verify JWT token → extract user_id

3. Session Retrieval
   ├─ Check Redis cache for session messages (cache-aside)
   └─ [Miss?] Load from PostgreSQL, update Redis

4. Agent Invocation
   ├─ Build prompt with:
   │  ├─ User message
   │  ├─ Previous conversation history
   │  └─ Available tools (from tool registry)
   ├─ Send to OpenAI LLM with `tools=[...]`
   └─ LLM returns response + optional tool_call

5. Tool Execution (if needed)
   ├─ LLM says: use "weather_lookup" tool
   ├─ Executor resolves: registry["weather_lookup"]
   ├─ Call tool.run({"city": "NYC"})
   └─ Get result: "Clear skies, 72°F"

6. Follow-up Answer (if tool was used)
   ├─ Re-invoke LLM: "Here's the tool result, synthesize final answer"
   └─ LLM returns user-friendly response

7. Memory Persistence (Write-Through)
   ├─ Save to PostgreSQL (authoritative)
   └─ Update Redis cache (for next turn speed)

8. HTTP Response
   {
     "session_id": "sess-abc123",
     "type": "text",
     "content": "It's sunny in NYC, 72°F and clear skies.",
     "metadata": {
       "confidence": 0.95,
       "sources": ["weather_tool"],
       "timestamp": "2026-03-21T15:30:00Z"
     }
   }
```

---

## Technology Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **API Framework** | FastAPI + Pydantic | Type-safe, auto-doc, async support |
| **LLM Integration** | OpenAI SDK | Native function calling for tool use |
| **Short-term Memory** | Redis 7 | Sub-millisecond reads, pub/sub for events |
| **Long-term Storage** | PostgreSQL 16 | ACID transactions, complex queries, audit trails |
| **Document Storage** | MinIO | S3-compatible, scalable, self-hosted |
| **Event Queue** | RabbitMQ 3.13 | Reliable message delivery, dead letter queues |
| **Authentication** | JWT + bcrypt | Stateless, secure, standard |
| **Runtime** | Python 3.12 | Type hints, performance, ecosystem |
| **Deployment** | Docker Compose | Local dev ≈ prod environment |

---

## Prerequisites & Setup

### System Requirements
- Python 3.12+
- Docker & Docker Compose
- 2GB RAM minimum (4GB recommended)
- OpenAI API key (or compatible: Ollama, Azure OpenAI, etc.)

### Local Development Setup

```bash
# 1. Clone & environment
git clone <repo>
cd agent-assistant
cp .env.example .env
# Edit .env: add OPENAI_API_KEY

# 2. Install dependencies
uv sync --dev

# 3. Start infrastructure (Docker)
docker compose up -d postgres redis rabbitmq minio

# 4. Verify health
docker compose ps
# All 4 containers should show "healthy"

# 5. Start API server
uv run uvicorn main:app --reload
# Visit http://localhost:8000/docs for OpenAPI UI

# 6. In another terminal, start document consumer worker
uv run python -m app.workers.document_uploaded_consumer
```

---

## Configuration

All settings are environment-based (12-factor app):

```env
# LLM Configuration
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4-mini
OPENAI_BASE_URL=                    # Leave empty for OpenAI, set for Ollama/Azure

# Database & Cache
DATABASE_URL=postgresql+psycopg://agent_user:agent_password@localhost:5432/agent_assistant
REDIS_URL=redis://localhost:6379/0
REDIS_CHAT_CACHE_TTL_SECONDS=3600   # 1 hour cache for active sessions

# Message Queue
RABBITMQ_URL=amqp://guest:guest@localhost:5672/%2F
RABBITMQ_DOCUMENT_EXCHANGE=documents.exchange
RABBITMQ_DOCUMENT_QUEUE=documents.uploaded.queue

# Document Storage
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=documents
DOCUMENT_CHUNK_SIZE_BYTES=1048576   # 1MB chunks

# Security
JWT_SECRET_KEY=your-long-random-secret-key
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60

# Logging
LOG_LEVEL=INFO
```

---

## API Endpoints

### User & Auth
```
POST   /v1/users/register              Create user account
POST   /v1/users/login                 Get JWT access token
GET    /v1/users/me                    Get current user profile
```

### Chat & Sessions
```
POST   /v1/agent/sessions              Create new conversation session
POST   /v1/agent/chat                  Send message, get AI response
DELETE /v1/agent/sessions/{session_id} Clear conversation history
```

### Documents
```
POST   /v1/documents/uploads           Upload file, chunk & index
```

### Health & Monitoring
```
GET    /health                         Service health check
GET    /                               API info
```

---

## Testing

```bash
# Run all tests
uv run pytest -q

# Run specific test file
uv run pytest tests/test_chat.py -v

# Run with coverage
uv run pytest --cov=app tests/

# Test without external services (all mocked)
# No Docker required!
```

Tests follow layered approach:
- **Unit tests**: Document chunking, tool execution, memory caching
- **Integration tests**: Full chat flow with mocked LLM
- **API tests**: HTTP endpoints, auth, serialization

---

## Troubleshooting

### Redis Connection Refused
```bash
docker compose logs redis
docker compose restart redis
```

### PostgreSQL won't start
```bash
# Clear old volume
docker compose down -v
docker compose up -d postgres
# Wait 30s for initialization
```

### Documents not being consumed
```bash
# Check RabbitMQ management UI
open http://localhost:15672  # user: guest, pass: guest

# Ensure consumer is running
ps aux | grep document_uploaded_consumer

# Check logs
docker compose logs rabbitmq
```

---

## Production Deployment

For production, consider:

1. **Scalability**
   - Run multiple FastAPI instances behind load balancer (nginx/HAProxy)
   - Add multiple consumer workers for document processing
   - Use managed PostgreSQL/Redis (AWS RDS, Redis Cloud)

2. **Security**
   - TLS/HTTPS everywhere
   - API rate limiting & auth token rotation
   - Secrets in HashiCorp Vault (not .env)
   - Audit logging to separate system

3. **Monitoring**
   - Prometheus metrics (response time, tool execution time)
   - ELK stack or CloudWatch for logs
   - Sentry for error tracking
   - PagerDuty alerts for critical failures

4. **Observability**
   - Request tracing (Jaeger/DataDog)
   - LLM call tracking (cost, latency, token usage)
   - Document processing pipeline metrics

---

## Contributing

Contributions welcome! Follow these principles:

- **Keep layers separate** — Don't import services from HTTP layer
- **Use protocols for abstractions** — Enable testing without full implementations
- **Add tests first** — TDD approach for business logic
- **Document trade-offs** — Why this decision vs. alternatives?
- **Log at the right level** — DEBUG for flow, INFO for business events, ERROR for failures

---

## License

MIT


