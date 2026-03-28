# Libs Simplification Plan

## Current Issues

### 1. Double Nesting (Like app/app before)
```
libs/core/
├── pyproject.toml
└── core/              # ← Duplicate nesting
    ├── __init__.py
    ├── config.py
    └── ...
```

### 2. pyproject.toml Still Needed

**YES, you need them even without publishing because:**
- ✅ uv workspace uses them to resolve dependencies
- ✅ Docker builds need them (`pip install -e libs/core`)
- ✅ They define inter-package dependencies (e.g., agents depends on core + infra)

**BUT we can simplify them!**

## Solution: Flatten + Simplify

### Flatten Structure
```
libs/core/
├── pyproject.toml
├── __init__.py        # ← Direct, no nesting
├── config.py
├── schemas.py
└── ...
```

### Simplified pyproject.toml

**Minimum for workspace-only packages:**

```toml
# libs/core/pyproject.toml
[project]
name = "core"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic-settings>=2.8.0",
    "pydantic>=2.0.0",
    "structlog>=24.0.0",
    # ... only what THIS package needs
]

# NO build-system needed if not publishing!
# uv workspace can install with just [project]
```

**For packages with workspace dependencies:**

```toml
# libs/infra/pyproject.toml
[project]
name = "infra"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "core",           # ← Workspace dependency
    "openai>=1.70.0",
    # ...
]

[tool.uv.sources]
core = { workspace = true }  # ← Tell uv it's local
```

## Actions Needed

1. **Flatten each lib:**
   - Move `libs/core/core/*` → `libs/core/`
   - Move `libs/infra/infra/*` → `libs/infra/`
   - Move `libs/agents/agents/*` → `libs/agents/`
   - Move `libs/tools/tools/*` → `libs/tools/`

2. **Simplify pyproject.toml:**
   - Remove `[build-system]` (not publishing)
   - Remove `[tool.hatch.build.targets.wheel]` (not building wheels)
   - Keep only `[project]` and `[tool.uv.sources]`

3. **Update imports:**
   - Imports stay the same! (from core.config import ...)
   - Because libs are added to Python path by workspace

## Before vs After

### Before (Current)
```
libs/core/
├── pyproject.toml (28 lines, build config)
└── core/
    ├── __init__.py
    └── config.py

Import: from core.config import Settings ✅
```

### After (Flattened)
```
libs/core/
├── pyproject.toml (15 lines, deps only)
├── __init__.py
└── config.py

Import: from core.config import Settings ✅ (same!)
```

## Docker Implications

**Before flattening:**
```dockerfile
# Works
RUN pip install -e libs/core
```

**After flattening:**
```dockerfile
# Still works!
RUN pip install -e libs/core
```

No change needed in Dockerfiles!

## Recommendation

**YES, flatten the libs too!**
- Cleaner structure
- Simpler pyproject.toml files
- Same imports
- Same Docker builds
- Consistent with app/ and pipeline/ flattening
