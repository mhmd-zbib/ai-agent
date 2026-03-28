# Quick Start Guide

## ✅ Correct Setup (After Flattening)

### Project Structure
```
agent-assitant/                   # ← Always run commands from here!
├── .env                          # ← Environment variables (root level)
├── .env.example
├── compose.yaml
├── README.md
│
├── app/                          # FastAPI backend
│   ├── pyproject.toml
│   ├── main.py                  # ← Flattened! (was app/app/main.py)
│   ├── auth/
│   ├── chat/
│   ├── documents/
│   ├── health/
│   ├── memory/
│   └── search/
│
├── pipeline/                     # RabbitMQ worker
│   ├── pyproject.toml
│   ├── main.py                  # ← Flattened! (was pipeline/pipeline/main.py)
│   └── ingestion/
│
└── libs/                         # Shared workspace libraries (NOT published)
    ├── core/                    # Contracts & domain
    ├── infra/                   # Database, LLM, storage drivers
    ├── tools/                   # Tool registry & implementations  
    └── agents/                  # Agent library
```

## Running the Application

### Step 1: Environment Setup
```bash
# Copy template (if not done already)
cp .env.example .env

# Edit .env with your settings
nano .env   # or your preferred editor
```

### Step 2: Start Infrastructure
```bash
# Start postgres, redis, rabbitmq, minio, qdrant
docker compose up -d

# Verify services are running
docker compose ps
```

### Step 3: Install Dependencies
```bash
# Sync all workspace packages
uv sync
```

### Step 4: Run Migrations (if needed)
```bash
uv run alembic upgrade head
```

### Step 5: Start FastAPI App
```bash
# From project root:
uv run serve

# Or manually:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Start Worker (separate terminal)
```bash
# From project root:
python -m pipeline.main

# Or with uv:
uv run python -m pipeline.main
```

## Verification

```bash
# Health check
curl http://localhost:8000/health

# API Documentation
open http://localhost:8000/docs

# Test chat endpoint (with auth)
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"message": "Hello!"}'
```

## Important Notes

1. **Always run from project root** (`/Users/mohammadzbib/Development/personal/agent-assitant/`)
   - The `.env` file is loaded from current working directory
   - Workspace imports expect to be run from root

2. **Directory structure is now flat**:
   - ✅ `app/main.py` (not `app/app/main.py`)
   - ✅ `pipeline/main.py` (not `pipeline/pipeline/main.py`)

3. **Imports still use package names**:
   - `from app.auth import ...` ✅ (works!)
   - `from pipeline.ingestion import ...` ✅ (works!)
   - Run command: `uvicorn app.main:app` (not `uvicorn main:app`)

4. **Libs are workspace-only**:
   - NOT published to PyPI
   - Shared locally between app & pipeline
   - Managed by uv workspace

## Convenience Scripts

### app/pyproject.toml
```toml
[project.scripts]
serve = "uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
serve-prod = "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"
```

Run with: `uv run serve` or `uv run serve-prod`

### For pipeline
No script needed, just run:
```bash
python -m pipeline.main
```

## Troubleshooting

**Error: "ModuleNotFoundError: No module named 'app'"**
- ✅ Fix: Run from project root, not from inside `app/`

**Error: ".env file not found"**
- ✅ Fix: Ensure `.env` is in project root
- ✅ Fix: Run commands from project root

**Error: "Connection refused" for database**
- ✅ Fix: Start docker services: `docker compose up -d`
- ✅ Fix: Check DATABASE_URL in `.env` matches compose.yaml

**Import errors after flattening**
- ✅ Fix: Re-sync workspace: `uv sync`
- ✅ Fix: Clear pycache: `find . -name "__pycache__" -exec rm -rf {} +`
