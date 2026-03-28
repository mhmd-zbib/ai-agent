# Libs Structure Issue & Fix

## Problem

After flattening libs, imports broke because:

1. **Old structure (working)**:
   ```
   libs/core/
   ├── pyproject.toml
   └── core/                    # Package directory
       ├── __init__.py          # from core.config import ...
       └── config.py
   ```

2. **Flattened (broken)**:
   ```
   libs/core/
   ├── pyproject.toml
   ├── __init__.py              # from core.config import ... ❌ (no core/)
   └── config.py
   ```

The __init__.py files have `from core.config import ...` but there's no `core/` subdirectory anymore!

## Solution: Keep Nested Structure for Libs

**Why libs NEED nesting** (unlike app/pipeline):
- Libs are importable packages (`import core`, `import tools`)
- Package name (core) must match directory name
- __init__.py uses absolute imports (`from core.x import`)
- This is standard Python package structure

**Why app/pipeline DON'T need nesting**:
- They're applications, not libraries
- Imports use package prefix (`from app.auth import`)
- Run from root directory
- Workspace makes them importable

## Correct Final Structure

```
agent-assitant/
├── .env
│
├── app/                       # ← FLAT (application)
│   ├── pyproject.toml
│   ├── main.py
│   └── auth/
│
├── pipeline/                  # ← FLAT (application)  
│   ├── pyproject.toml
│   ├── main.py
│   └── ingestion/
│
└── libs/                      # ← NESTED (packages)
    ├── core/
    │   ├── pyproject.toml
    │   └── core/              # ← Package dir (needed!)
    │       ├── __init__.py
    │       └── config.py
    │
    ├── infra/
    │   ├── pyproject.toml
    │   └── infra/             # ← Package dir (needed!)
    │
    ├── tools/
    │   ├── pyproject.toml
    │   └── tools/             # ← Package dir (needed!)
    │
    └── agents/
        ├── pyproject.toml
        └── agents/            # ← Package dir (needed!)
```

## Action: Restore Nesting for Libs

We need to move files back:
- libs/core/* → libs/core/core/
- libs/infra/* → libs/infra/infra/
- libs/tools/* → libs/tools/tools/
- libs/agents/* → libs/agents/agents/
