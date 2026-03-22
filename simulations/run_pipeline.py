#!/usr/bin/env python3
"""
Run once — simulates the full RAG ingestion pipeline end to end.

    uv run simulations/run_pipeline.py
"""

import json
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# ✏️  Config — edit these if needed
# ---------------------------------------------------------------------------

API_BASE = "http://localhost:8000"
DATABASE_URL = "postgresql://agent_user:agent_password@localhost:5432/agent_assistant"
CHUNK_BYTES = 1024 * 1024  # 1 MB upload chunks (matches DOCUMENT_CHUNK_SIZE_BYTES)

EMAIL = "zbib@gmail.com"
PASSWORD = "zbib123321"
UNIVERSITY = "LIU"       # LIU | AUB | LAU
MAJOR = "COMPUTER_SCIENCE"
COURSE_CODE = "PHAR205"

FILE = Path(__file__).parent / "phar.pdf"  # swap to any .pdf / .docx / .txt

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http(method, url, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code}: {e.read().decode()}")
        raise


def put_bytes(url, data, content_type):
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": content_type}, method="PUT"
    )
    with urllib.request.urlopen(req) as r:
        r.read()


# ---------------------------------------------------------------------------
# Postgres
# ---------------------------------------------------------------------------


def get_document_id(upload_id):
    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT document_id FROM documents WHERE upload_id = %s", (upload_id,)
        ).fetchone()
    return row[0] if row else None


def watch(document_id, timeout=180):
    import psycopg

    STAGES = [
        "uploaded",
        "parsing",
        "parsed",
        "chunking",
        "chunked",
        "embedding",
        "storing",
        "completed",
    ]

    print(f"\n  document_id → {document_id}")
    print(f"  {'─' * 54}")
    print(f"  {'TIME':8}  {'STATUS':<12}  DETAIL")
    print(f"  {'─' * 54}")

    last = None
    deadline = time.monotonic() + timeout

    with psycopg.connect(DATABASE_URL) as conn:
        while time.monotonic() < deadline:
            row = conn.execute(
                "SELECT status, total_chunks, error_message, updated_at "
                "FROM documents WHERE document_id = %s",
                (document_id,),
            ).fetchone()

            if row:
                status, total_chunks, error_msg, updated_at = row
                if status != last:
                    ts = updated_at.strftime("%H:%M:%S") if updated_at else "?"
                    pos = (STAGES.index(status) + 1) if status in STAGES else 0
                    bar = "█" * pos + "░" * (len(STAGES) - pos)
                    detail = f"chunks={total_chunks}" if total_chunks else ""
                    if error_msg:
                        detail = f"ERROR: {error_msg[:60]}"
                    print(f"  {ts}  {status:<12}  {detail}")
                    print(f"           [{bar}]")
                    last = status

                if status in ("completed", "failed"):
                    break

            time.sleep(1)

    print(f"  {'─' * 54}")
    return last == "completed"


def print_chunks(document_id):
    import psycopg

    with psycopg.connect(DATABASE_URL) as conn:
        rows = conn.execute(
            "SELECT chunk_index, chunk_id, source_page, stored_at "
            "FROM document_chunks WHERE document_id = %s ORDER BY chunk_index",
            (document_id,),
        ).fetchall()

    print(f"\n  Chunks stored in vector DB ({len(rows)} total)")
    print(f"  {'─' * 54}")
    for idx, chunk_id, page, stored_at in rows:
        ts = stored_at.strftime("%H:%M:%S") if stored_at else "?"
        pg = f"p{page}" if page else "  "
        print(f"  [{idx:3d}]  {chunk_id[:40]}  {pg}  {ts}")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

file_bytes = FILE.read_bytes()
content_type = (
    "application/pdf"
    if FILE.suffix == ".pdf"
    else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if FILE.suffix == ".docx"
    else "text/plain"
)
parts = [
    file_bytes[i * CHUNK_BYTES : (i + 1) * CHUNK_BYTES]
    for i in range(max(1, math.ceil(len(file_bytes) / CHUNK_BYTES)))
]

print(f"\n  {'═' * 54}")
print("  RAG Pipeline Simulation")
print(f"  file    : {FILE.name}  ({len(file_bytes):,} bytes)")
print(f"  api     : {API_BASE}")
print(f"  {'═' * 54}\n")

# 1. Register
print("[1] Register")
try:
    http(
        "POST",
        f"{API_BASE}/v1/users/register",
        {"email": EMAIL, "password": PASSWORD, "university": UNIVERSITY, "major": MAJOR},
    )
    print("    registered")
except urllib.error.HTTPError:
    print("    already exists")

# 2. Login
print("[2] Login")
token = http(
    "POST", f"{API_BASE}/v1/users/login", {"email": EMAIL, "password": PASSWORD}
)["access_token"]
print(f"    token: {token[:32]}…")

# 3. Initiate upload
print("[3] Initiate upload")
resp = http(
    "POST",
    f"{API_BASE}/v1/documents/uploads",
    {
        "file_name": FILE.name,
        "content_type": content_type,
        "file_size_bytes": len(file_bytes),
        "chunk_size_bytes": CHUNK_BYTES,
    },
    token=token,
)
upload_id = resp["upload_id"]
presigned = resp["chunks"]
print(f"    upload_id   : {upload_id}")
print(f"    upload_parts: {len(presigned)}")

# 4. PUT to MinIO
print("[4] Upload to MinIO")
for meta in presigned:
    i = meta["chunk_index"]
    print(f"    PUT part {i} → {meta['object_key']}")
    put_bytes(meta["presigned_url"], parts[i], content_type)
    print(f"    ✓ part {i} stored")

# 5. Complete
print("[5] Complete upload")
resp = http(
    "POST",
    f"{API_BASE}/v1/documents/uploads/{upload_id}/complete",
    {
        "file_name": FILE.name,
        "content_type": content_type,
        "chunks": [
            {"chunk_index": i, "size_bytes": len(parts[i])} for i in range(len(parts))
        ],
        "course_code": COURSE_CODE,
        "university_name": UNIVERSITY,
    },
    token=token,
)
print(f"    event_published: {resp.get('event_published')}")

# Resolve document_id
print("    waiting for Postgres record…", end=" ", flush=True)
document_id = None
for _ in range(15):
    document_id = get_document_id(upload_id)
    if document_id:
        break
    time.sleep(0.5)

if not document_id:
    print("NOT FOUND — is the API running and DATABASE_URL correct?")
    sys.exit(1)
print("found")

# 6. Watch pipeline
print("\n[6] Watching pipeline (Postgres polling)")
completed = watch(document_id)

if completed:
    print_chunks(document_id)
    print("\n  ✓ Done.\n")
else:
    print(
        "\n  ✗ Pipeline did not complete — check API logs and RabbitMQ UI → http://localhost:15672\n"
    )
    sys.exit(1)
