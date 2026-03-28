# Tools Module Analysis: Should It Move to libs/?

## Current State Analysis

### Tools Module Location
```
app/app/tools/
├── __init__.py          (get_tool_registry factory)
├── base.py              (BaseTool abstract class)
├── exceptions.py        (ToolNotFoundError, ToolExecutionError)
├── registry.py          (ToolRegistry class)
└── implementations/
    ├── calculator.py
    ├── datetime_now.py
    ├── document_lookup.py
    ├── scientific_calc.py
    ├── weather.py
    └── web_search.py
```

### Dependencies Analysis

**tools/ has ZERO dependencies on app/**
- ✅ No imports from `app.chat`, `app.memory`, `app.search`, etc.
- ✅ Only imports: `core.config` (get_settings for ENABLE_DEMO_TOOLS)
- ✅ All imports are either: `ast`, `operator`, `math`, `requests` (external), etc.
- ✅ No FastAPI, no HTTP layer, no database access

**tools/ IS used by:**
- `app.main` — imports `get_tool_registry()` for orchestrator creation
- `agents.orchestrator.agent` — accepts `tool_registry` as constructor parameter
- `agents.document.agent` — accepts `tool_registry` as constructor parameter

### Key Insight: Tools ARE Already Library-Like

The tools module is **NOT tightly coupled to the app layer**:
1. ✅ No HTTP dependencies (FastAPI, routers, request/response)
2. ✅ No app-specific business logic
3. ✅ Pure abstraction: BaseTool ABC + implementations
4. ✅ Used by agents (which are in libs/)
5. ✅ Registry pattern (dependency injection friendly)

---

## Recommendation: YES, Move to libs/tools

### Why It Should Move

**1. Architectural Purity** 
- Tools are infrastructure abstractions, not HTTP concerns
- Should live with other reusable libraries, not HTTP API layer
- Agents should not import from `app.*` to get tools

**2. Agents Need Tools**
- Current: Agents import from `app.tools` (dependency violation!)
- Goal: Agents in `libs/agents/` should depend on `libs/tools/`
- This is a **pure inversion**: right now app depends on libs (agents) AND libs should depend on app (tools)

**3. Reusability**
- Other services could use tools without importing from app
- New workers, scripts, or services can access tools independently
- Non-HTTP contexts (CLI, batch jobs) can use tool registry

**4. Dependency Graph Clarity**
```
CURRENT (problematic):
core → infra → agents → app (agents pull tools from app!)

PROPOSED (clean):
core
  ↓
infra
  ↓
libs/tools ← Pure tool abstraction
  ↓
agents (uses tools)
  ↓
app (uses agents)
```

**5. It's Already Testable in Isolation**
- No app-specific configuration needed
- Can test tools without running FastAPI
- Can mock tool registry easily

---

## Migration Plan

### Step 1: Create libs/tools/

```
libs/
├── core/
├── infra/
├── agents/
└── tools/           ← NEW
    ├── pyproject.toml
    └── tools/
        ├── __init__.py
        ├── base.py
        ├── exceptions.py
        ├── registry.py
        └── implementations/
            ├── __init__.py
            ├── calculator.py
            ├── datetime_now.py
            ├── document_lookup.py
            ├── scientific_calc.py
            ├── weather.py
            └── web_search.py
```

### Step 2: Dependencies in libs/tools/pyproject.toml

```toml
[project]
name = "tools"
dependencies = [
    "core",          # For get_settings (ENABLE_DEMO_TOOLS)
    "requests>=2.31.0",
    "numpy>=1.26.0",
    "scipy>=1.13.0",
    "sympy>=1.13.0",
]
```

### Step 3: Update Imports

**Before:**
```python
# In agents/
from app.tools import get_tool_registry

# In app/main.py
from app.tools import get_tool_registry
```

**After:**
```python
# In agents/ (now same level)
from tools import get_tool_registry

# In app/main.py (now depends on libs/)
from tools import get_tool_registry
```

### Step 4: Update app/pyproject.toml

Add `tools` as dependency:
```toml
dependencies = [
    "core",
    "infra",
    "agents",
    "tools",  ← ADD THIS
    "fastapi>=0.135.1",
    ...
]
```

### Step 5: Update Root pyproject.toml

```toml
[tool.uv.workspace]
members = ["app", "pipeline", "libs/core", "libs/infra", "libs/agents", "libs/tools"]
```

---

## What Changes, What Doesn't

### Changes Required
- ✅ Move `app/app/tools/` → `libs/tools/tools/`
- ✅ Update imports in `app/app/main.py`: `from app.tools` → `from tools`
- ✅ Update imports in `libs/agents/`: `from app.tools` → `from tools`
- ✅ Add `libs/tools/pyproject.toml`
- ✅ Update `pyproject.toml` workspace members
- ✅ Update `app/app/pyproject.toml` to depend on tools

### No Changes Needed
- ✅ Tool implementations (no business logic changes)
- ✅ BaseTool interface (same contract)
- ✅ Registry pattern (same usage)
- ✅ Config access (core.config still works)
- ✅ API endpoints (none currently, tools are not exposed)

---

## Code Impact Analysis

### Files to Update

1. **`app/app/main.py`** (1 import line)
   ```diff
   - from app.tools import get_tool_registry
   + from tools import get_tool_registry
   ```

2. **`libs/agents/agents/core/base.py`** (if importing tools)
   ```diff
   - from app.tools.registry import ToolRegistry
   + from tools.registry import ToolRegistry
   ```

3. **`libs/agents/agents/orchestrator/agent.py`** (if importing tools)
   ```diff
   - from app.tools import get_tool_registry
   + from tools import get_tool_registry
   ```

4. **Create `libs/tools/pyproject.toml`** (15 lines)
5. **Update `pyproject.toml`** (add `libs/tools` to members)
6. **Update `app/app/pyproject.toml`** (add `tools` dependency)
7. **Create `libs/tools/tools/__init__.py`** (with exports)

### Zero Breaking Changes
- Same registry interface
- Same tool implementations
- Same exception handling
- Same configuration

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| Import path confusion | Low | Clear documentation, consistent naming |
| Circular dependency | Low | tools → core only (no backward deps) |
| Tools can't access app context | Low | Tools don't need app context (design goal) |

---

## Final Recommendation

✅ **YES, move tools to libs/tools/**

**Reasoning:**
1. **Already designed as library** — No app-specific coupling
2. **Agents need it** — Current dependency inversion is wrong
3. **Clean architecture** — Infrastructure abstraction belongs in libs
4. **Low migration cost** — ~5 files to update, all simple import changes
5. **Improves reusability** — Other services can use tools independently
6. **Zero breaking changes** — Same public API

**Execution Effort:** ~30 minutes
- Create libs/tools structure
- Move files
- Update imports
- Test

**Priority:** Medium (nice-to-have, but improves architecture clarity)

---

## If You Disagree

Keep tools in `app/` only if:
- Tools will always be tightly coupled to HTTP API concerns
- No other services will ever need tools
- You want all composition logic centralized in app

Otherwise, tools should move to libs for proper separation of concerns.

