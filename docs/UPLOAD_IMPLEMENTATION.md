# Document Upload Flow - Implementation Summary

## What Was Built

Complete end-to-end document upload system with the following 3-step flow:

### Step 1: Client Initiates Upload
- **Endpoint:** `POST /v1/documents/initiate-upload`
- **What happens:**
  - Client sends document metadata (name, size, MIME type, chunking strategy)
  - Backend creates upload session in Redis
  - Backend generates presigned URL for MinIO bucket
  - Backend returns: session ID, chunk size, max chunks, expiration
  
### Step 2: Client Uploads Chunks & Notifies Backend
- **Upload:** Client directly uploads chunks to MinIO using presigned URL
- **Notify:** `POST /v1/documents/chunk-received` for each chunk
- **What happens:**
  - Backend records chunk metadata in Redis
  - Backend validates chunk hash
  - Backend returns success response

### Step 3: Client Completes Upload
- **Endpoint:** `POST /v1/documents/complete-upload`
- **What happens:**
  - Backend validates all chunks were received
  - Backend publishes `DocumentUploadedEvent` to RabbitMQ
  - Pipeline consumer picks up event immediately
  - Backend returns job ID for tracking

---

## Files Created

### App Layer (Backend HTTP API)

**`app/documents/schemas.py`** (217 lines)
- `BucketInfoRequest` — Client request for credentials
- `BucketInfoResponse` — Bucket details to client
- `ChunkUploadNotification` — Chunk completion notification
- `DocumentUploadCompleteRequest` — Upload completion request
- `UploadSession` — Session data model (stored in Redis)

**`app/documents/repository.py`** (155 lines)
- `UploadSessionRepository` — Redis session storage (TTL: 1 hour)
  - `create_session()` — Create new upload session
  - `get_session()` — Retrieve session
  - `record_chunk_received()` — Track chunk receipt
  - `mark_complete()` / `mark_failed()` — Update status
- `MinIOBucketRepository` — S3/MinIO bucket operations
  - `get_presigned_upload_url()` — Generate direct upload URLs
  - `get_document()` / `upload_document()` — Fetch/store docs

**`app/documents/service.py`** (187 lines)
- `DocumentUploadService` — Orchestrates entire upload flow
  - `initiate_upload()` — Step 1: Return credentials
  - `notify_chunk_received()` — Step 2: Record chunks
  - `complete_upload()` — Step 3: Publish event + trigger pipeline

**`app/documents/router.py`** (156 lines)
- `POST /v1/documents/initiate-upload`
- `POST /v1/documents/chunk-received`
- `POST /v1/documents/complete-upload`

### Updated Files

**`app/app/main.py`** (updated)
- Added imports: `DocumentUploadService`, `MinIOBucketRepository`, `UploadSessionRepository`, `RabbitMQPublisher`
- Added `create_document_upload_service()` factory function
- Register service in `_startup_services()`
- Register documents router in `create_app()`

**`app/app/dependencies.py`** (updated)
- Added `get_document_upload_service()` dependency provider

**`UPLOAD_FLOW.md`** (comprehensive documentation)
- Architecture diagram
- API endpoint details with examples
- Client usage pseudocode
- Error handling & recovery
- Configuration requirements
- Testing guide with curl commands

---

## How It Works

```
CLIENT                          BACKEND (app)              RABBITMQ              PIPELINE
  │                                 │                          │                    │
  ├─ POST /initiate-upload  ─────→  │                          │                    │
  │                         ←─ session_id, presigned_url        │                    │
  │                                  │ (store in Redis)         │                    │
  │                                  │                          │                    │
  ├─ Upload to MinIO  ───────────────→ (direct upload)          │                    │
  │                                                              │                    │
  ├─ POST /chunk-received (x N) ───→ │                          │                    │
  │                         ←─ ack    │ (record chunks in Redis) │                    │
  │                                  │                          │                    │
  ├─ POST /complete-upload  ────────→ │                          │                    │
  │                         ←─ job_id │ (validate, publish event)│                    │
  │                                  │                          │                    │
  │                                  ├─ publish DocumentUploadedEvent ─────────→     │
  │                                  │                          │       consume      │
  │                                  │                          │                    ├─ Fetch doc from MinIO
  │                                  │                          │                    ├─ Parse document
  │                                  │                          │                    ├─ Chunk with strategy
  │                                  │                          │                    ├─ Generate metadata
  │                                  │                          │                    ├─ Embed & store
  │                                  │                          │                    ├─ Complete
```

---

## Key Features

✅ **Chunked Upload** — Support for large files (5MB chunks by default)  
✅ **Direct S3/MinIO** — Presigned URLs bypass server (faster, less load)  
✅ **Session Management** — Redis-backed with 1-hour TTL  
✅ **Async Pipeline** — RabbitMQ event triggers background processing  
✅ **Chunk Validation** — Hash verification for data integrity  
✅ **Error Recovery** — Automatic cleanup, clear error messages  
✅ **Monitoring** — Job IDs for tracking through pipeline  
✅ **Configurable** — Chunking strategies, chunk sizes, TTLs  

---

## Testing

### Quick Test with curl

```bash
# 1. Get credentials
SESSION=$(curl -X POST http://localhost:8000/v1/documents/initiate-upload \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"document_name":"test.pdf","content_type":"application/pdf","total_size_bytes":1000000,"chunking_strategy":"fixed"}' \
  | jq -r '.upload_session_id')

# 2. Upload chunk(s) to MinIO (using presigned_url from response)
# 3. Notify backend
curl -X POST http://localhost:8000/v1/documents/chunk-received \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"upload_session_id\":\"$SESSION\",\"chunk_number\":1,\"chunk_hash\":\"abc\",\"chunk_size_bytes\":1000000}"

# 4. Complete upload (triggers ingestion)
curl -X POST http://localhost:8000/v1/documents/complete-upload \
  -H "Authorization: Bearer $TOKEN" \
  -d "{\"upload_session_id\":\"$SESSION\",\"total_chunks\":1,\"file_hash\":\"xyz\",\"course_id\":\"course_123\"}"
```

---

## Documentation

- **`UPLOAD_FLOW.md`** — Complete API documentation with examples
- **Code comments** — Docstrings on all classes/methods
- **Type hints** — Full type annotations for clarity
- **Error messages** — Descriptive messages for debugging

---

## Architecture Benefits

1. **Scalability:** Multiple pipeline workers consume same event (fan-out)
2. **Reliability:** RabbitMQ ensures no events are lost; DLQ for failures
3. **Performance:** Direct bucket uploads bypass server bottleneck
4. **Flexibility:** Chunking strategy passed through entire pipeline
5. **Monitoring:** Job IDs enable end-to-end tracking
6. **Separation:** Upload API decoupled from ingestion processing

---

## Next Steps (Optional Enhancements)

- [ ] Add progress tracking (e.g., `/v1/documents/jobs/{job_id}/status`)
- [ ] Implement resume for failed uploads (partial re-upload)
- [ ] Add file size limits and quotas per user
- [ ] Support multiple file formats (Office, images, etc.)
- [ ] Add webhook callbacks for pipeline completion
- [ ] Implement virus scanning pre-upload

---

**Status:** ✅ Ready for integration and testing!

