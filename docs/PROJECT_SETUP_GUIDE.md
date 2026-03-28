# Project Setup & Configuration Guide

## Issue Analysis & Solutions

### 1. ✅ .env File Location - CORRECT AS-IS

**Current Setup (CORRECT):**
```
/Users/mohammadzbib/Development/personal/agent-assitant/.env  ← Root directory
```

**Why this is correct:**
- Pydantic Settings in `libs/core/core/config.py` is configured to load `.env` from the current working directory
- When you run `uvicorn app.main:app` from the root, it automatically finds `.env`
- All workspace packages (app, pipeline, libs/*) share the same environment variables
- This is the standard monorepo pattern

**Configuration:**
```python
# libs/core/core/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",              # Looks in CWD (current working directory)
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )
```

**DO NOT:**
- ❌ Create separate `.env` files in `app/` or `pipeline/`
- ❌ Duplicate environment variables across multiple files

**DO:**
- ✅ Keep single `.env` in project root
- ✅ Use `.env.example` as template (already exists)
- ✅ Run all commands from project root directory

---

### 2. ⚠️ Directory Structure - NEEDS DISCUSSION

**Current Structure:**
```
agent-assitant/
├── app/
│   ├── pyproject.toml          # Package metadata
│   └── app/                    # ← Double nesting
│       ├── main.py
│       ├── auth/
│       ├── chat/
│       └── ...
│
└── pipeline/
    ├── pyproject.toml          # Package metadata
    └── pipeline/               # ← Double nesting
        ├── main.py
        └── ingestion/
```

**Why this structure exists:**
This is a valid Python packaging pattern where:
- Outer `app/` = workspace member directory + package config
- Inner `app/` = actual Python package (importable as `import app`)

**Pros:**
✅ Standard Python packaging (used by many projects)
✅ Clear separation: config vs code
✅ Works correctly with uv workspace
✅ Package name matches directory

**Cons:**
❌ Confusing for newcomers
❌ Extra nesting level
❌ Not strictly necessary for workspace

**Alternative (Flatter Structure):**
```
agent-assitant/
├── app/
│   ├── pyproject.toml
│   ├── main.py              # ← No double nesting
│   ├── auth/
│   └── ...
```

**To change this would require:**
1. Moving all files from `app/app/*` → `app/*`
2. Moving all files from `pipeline/pipeline/*` → `pipeline/*`
3. Updating all imports (currently `from app.auth` → would stay same)
4. Updating package configuration in pyproject.toml

**Recommendation:** Keep current structure for now (it's valid). If you want to flatten, we can do it in a separate refactor.

---

### 3. ❌ Running the App - NEEDS FIX

**Current app/main.py (line 293):**
```python
app = create_app()  # ✅ App instance is created
```

**Problem:** To run with uvicorn, you need correct module path.

**How to Run (from project root):**

```bash
# Current working setup:
cd /Users/mohammadzbib/Development/personal/agent-assitant

# Start FastAPI app:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or using uv:
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Module Path Breakdown:**
- `app.main` = module path (app/ package, main.py file)
- `:app` = variable name of FastAPI instance
- Full path: `app/app/main.py` → variable `app`

**The main.py is correct!** It already has:
```python
app = create_app()  # Line 293 - creates FastAPI instance
```

**What's needed in pyproject.toml:**

Check if there's a script entry for easier running:

```toml
# app/pyproject.toml (ADD THIS if not present)
[project.scripts]
serve = "uvicorn app.main:app --reload"
```

Then you can run: `uv run serve`

---

## Complete Startup Guide

### Prerequisites
```bash
# 1. Copy .env.example to .env
cp .env.example .env

# 2. Edit .env with your settings
# For local development with Ollama:
OPENAI_API_KEY=not-needed
OPENAI_MODEL=gemma3:270m
OPENAI_BASE_URL=http://localhost:11434/v1

# Database
DATABASE_URL=postgresql+psycopg://agent_user:agent_password@localhost:5432/agent_assistant
REDIS_URL=redis://localhost:6379/0

# 3. Start infrastructure
docker compose up -d
```

### Start the App

```bash
# From project root:
cd /Users/mohammadzbib/Development/personal/agent-assitant

# Sync dependencies first:
uv sync

# Run database migrations (if using Alembic):
uv run alembic upgrade head

# Start FastAPI server:
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or if you add the script entry:
uv run serve
```

### Start the Worker (Pipeline)

```bash
# In a separate terminal:
cd /Users/mohammadzbib/Development/personal/agent-assitant

# Start RabbitMQ consumer:
uv run python -m pipeline.main

# Or add to pipeline/pyproject.toml:
# [project.scripts]
# worker = "python -m pipeline.main"

# Then run:
uv run worker
```

### Verify Setup

```bash
# Health check:
curl http://localhost:8000/health

# Check API docs:
open http://localhost:8000/docs
```

---

## Summary of Fixes Needed

1. ✅ **.env location** - Already correct (root directory)

2. ⚠️ **Directory structure** - Current structure is valid but could be flattened
   - **Action:** Keep as-is for now (working correctly)
   - **Future:** Can flatten `app/app/` → `app/` if desired

3. ✅ **main.py setup** - Already correct!
   - **Action:** Just run with correct uvicorn command
   - **Optional:** Add script entries to pyproject.toml for convenience

---

## Recommended pyproject.toml Additions

**app/pyproject.toml:**
```toml
[project.scripts]
serve = "uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
serve-prod = "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4"
```

**pipeline/pyproject.toml:**
```toml
[project.scripts]
worker = "python -m pipeline.main"
```

Then you can run:
```bash
uv run serve      # Start FastAPI app
uv run worker     # Start RabbitMQ worker
```
