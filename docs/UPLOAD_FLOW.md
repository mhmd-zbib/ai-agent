# Document Upload Flow - Implementation Guide

## Overview

This implementation provides a complete chunked file upload workflow:

1. **Client initiates** → Backend returns bucket credentials
2. **Client uploads chunks** → To MinIO S3 bucket
3. **Client notifies backend** → For each chunk completion
4. **Client completes upload** → Backend publishes to RabbitMQ
5. **Pipeline consumer** → Fetches document from bucket and starts ingestion

---

## Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │
       ├─→ POST /v1/documents/initiate-upload (get bucket creds)
       │   ↓ returns: upload_session_id, presigned_url, chunk_size
       │
       ├─→ Upload chunks directly to MinIO bucket
       │   (Using presigned_url from response)
       │
       ├─→ POST /v1/documents/chunk-received (for each chunk)
       │   (Notify backend of chunk completion)
       │   ↓ backend records chunk metadata in Redis
       │
       ├─→ POST /v1/documents/complete-upload (all chunks done)
       │   ↓ backend publishes DocumentUploadedEvent to RabbitMQ
       │
       └─→ Response: ingestion_job_id (for tracking)

┌──────────────────┐
│   FastAPI App    │
│  (app/documents) │
└────────┬─────────┘
         │
         ├─→ Records upload session in Redis
         ├─→ Generates MinIO presigned URLs
         ├─→ Validates chunk completion
         └─→ Publishes events to RabbitMQ

┌─────────────────┐
│  RabbitMQ Bus   │
│ documents.fanout│  DocumentUploadedEvent
└────────┬────────┘
         │
         └─→ Fanout to pipeline workers

┌────────────────────┐
│ Pipeline Workers   │
│ (pipeline/main.py) │
└────────┬───────────┘
         │
         ├─→ Fetch document from MinIO bucket
         ├─→ Parse (PDF, Word, etc.)
         ├─→ Chunk with specified strategy
         ├─→ Generate metadata
         ├─→ Embed and store in vector DB
         └─→ Complete ingestion
```

---

## API Endpoints

### 1. Initiate Upload

**Endpoint:** `POST /v1/documents/initiate-upload`

**Request:**
```json
{
    "document_name": "lecture_notes.pdf",
    "content_type": "application/pdf",
    "total_size_bytes": 104857600,
    "chunking_strategy": "fixed"
}
```

**Response (200 OK):**
```json
{
    "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "bucket_name": "documents",
    "presigned_url": "http://localhost:9000/...",
    "chunk_size_bytes": 5242880,
    "max_chunks": 21,
    "expires_in_seconds": 3600,
    "metadata": {
        "content_type": "application/pdf",
        "chunking_strategy": "fixed"
    }
}
```

**Client Usage (Pseudocode):**
```javascript
// Step 1: Get upload credentials
const uploadInfo = await fetch('/v1/documents/initiate-upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        document_name: 'lecture_notes.pdf',
        content_type: 'application/pdf',
        total_size_bytes: file.size,
        chunking_strategy: 'fixed'
    })
}).then(r => r.json());

const { upload_session_id, chunk_size_bytes } = uploadInfo;
```

### 2. Notify Chunk Received

**Endpoint:** `POST /v1/documents/chunk-received`

**Request (for each chunk):**
```json
{
    "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "chunk_number": 1,
    "chunk_hash": "sha256:abc123def456...",
    "chunk_size_bytes": 5242880
}
```

**Response (200 OK):**
```json
{
    "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "chunk_number": 1,
    "status": "stored",
    "message": "Chunk 1 received and stored"
}
```

**Client Usage (Pseudocode):**
```javascript
// Step 2a: Upload chunk to MinIO (using presigned_url)
const chunkData = file.slice(0, chunk_size_bytes);
const formData = new FormData();
formData.append('file', chunkData);

await fetch(presigned_url, {
    method: 'POST',
    body: formData
});

// Step 2b: Notify backend of chunk completion
await fetch('/v1/documents/chunk-received', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        upload_session_id,
        chunk_number: 1,
        chunk_hash: await sha256(chunkData),
        chunk_size_bytes: chunkData.size
    })
});

// Repeat for remaining chunks...
```

### 3. Complete Upload

**Endpoint:** `POST /v1/documents/complete-upload`

**Request:**
```json
{
    "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "total_chunks": 21,
    "file_hash": "sha256:complete_file_hash...",
    "course_id": "course_123",
    "document_metadata": {
        "subject": "Mathematics",
        "level": "101",
        "term": "Spring2024"
    }
}
```

**Response (200 OK):**
```json
{
    "document_key": "uploads/user123/550e8400-e29b-41d4-a716-446655440000/lecture_notes.pdf",
    "ingestion_job_id": "job-uuid-12345",
    "status": "queued",
    "message": "Upload complete. Ingestion job job-uuid-12345 queued for processing."
}
```

**Client Usage (Pseudocode):**
```javascript
// Step 3: Complete upload
const completeResponse = await fetch('/v1/documents/complete-upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        upload_session_id,
        total_chunks: numChunks,
        file_hash: await sha256(entireFile),
        course_id: 'course_123',
        document_metadata: {
            subject: 'Mathematics',
            level: '101'
        }
    })
}).then(r => r.json());

const { ingestion_job_id } = completeResponse;
console.log(`Ingestion started: ${ingestion_job_id}`);
```

---

## Backend Implementation Details

### App Layer (`app/documents/`)

**schemas.py:**
- `BucketInfoRequest` — Client request for upload credentials
- `BucketInfoResponse` — Server response with bucket details
- `ChunkUploadNotification` — Chunk completion notification
- `DocumentUploadCompleteRequest` — Upload completion request
- `UploadSession` — Session metadata (stored in Redis)

**repository.py:**
- `UploadSessionRepository` — Session management in Redis (TTL: 1 hour)
- `MinIOBucketRepository` — S3/MinIO interactions (presigned URLs, get/upload)

**service.py:**
- `DocumentUploadService` — Orchestrates the 3-step flow
  1. `initiate_upload()` — Create session, return credentials
  2. `notify_chunk_received()` — Record chunk metadata
  3. `complete_upload()` — Publish DocumentUploadedEvent to RabbitMQ

**router.py:**
- `POST /v1/documents/initiate-upload` — Get upload credentials
- `POST /v1/documents/chunk-received` — Notify chunk completion
- `POST /v1/documents/complete-upload` — Trigger ingestion

### Pipeline Layer (`pipeline/`)

**main.py:**
- `RabbitMQConsumer` — Listens on `documents` fanout exchange
- `_handle_message()` — Processes `DocumentUploadedEvent`

**Event Flow:**
```
DocumentUploadedEvent (from RabbitMQ):
{
    "event_type": "DocumentUploadedEvent",
    "job_id": "job-uuid",
    "document_key": "uploads/user123/.../file.pdf",
    "document_name": "file.pdf",
    "content_type": "application/pdf",
    "user_id": "user123",
    "course_id": "course_123",
    "chunking_strategy": "fixed",
    "metadata": { ... }
}
                ↓
Pipeline consumer fetches document from MinIO
                ↓
Runs 4-stage ingestion:
1. Parser.parse() — Extract document structure
2. Chunker.chunk() — Apply chunking strategy
3. Metadata.generate() — Extract metadata
4. Storage.store() — Embed + upsert to vector DB
                ↓
Ingestion complete
```

---

## Key Design Decisions

### 1. **Redis for Session State**
- Upload sessions stored in Redis (1-hour TTL)
- Chunk receipt tracked as set of chunk numbers
- Automatic cleanup after expiration
- Fast lookup for validation

### 2. **RabbitMQ for Async Processing**
- `DocumentUploadedEvent` published after validation
- Multiple pipeline workers can consume (fan-out)
- Decouples upload API from ingestion processing
- DLQ for failed messages

### 3. **MinIO Direct Upload**
- Presigned URLs allow direct client→bucket uploads
- Reduces load on FastAPI server
- Faster, parallel chunk uploads
- No multipart rebuild on server

### 4. **Chunking Strategy Parameter**
- Client specifies chunking strategy upfront
- Passed through to pipeline for consistent processing
- Supports: `fixed`, `semantic`, `page_based`
- Enables optimization based on document type

### 5. **Validation Points**
- Chunk hash verification (MD5/SHA256)
- Complete file hash verification
- Chunk count validation
- Session expiration checks

---

## Error Handling

### HTTP Status Codes

| Code | Scenario | Action |
|------|----------|--------|
| 200 | Success | Proceed to next step |
| 400 | Validation failed (missing chunks) | Retry upload |
| 401 | Unauthorized | Refresh token, retry |
| 500 | Server error | Retry with backoff |

### Recovery Strategies

**If chunk upload fails:**
1. Retry failed chunk (use same chunk_number)
2. Backend updates Redis (overwrites old entry)
3. Proceed to next chunk

**If complete-upload fails:**
1. Retry complete-upload (idempotent)
2. Session still exists in Redis
3. RabbitMQ publishes duplicate event (idempotent in pipeline)

**If pipeline processing fails:**
1. Message goes to DLQ after N retries
2. Manual intervention required
3. Operator can republish or inspect logs

---

## Configuration Required

Add to `.env`:

```bash
# MinIO/S3
MINIO_ENDPOINT=http://localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=documents

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USERNAME=guest
RABBITMQ_PASSWORD=guest

# Upload settings
UPLOAD_SESSION_TTL_SECONDS=3600
UPLOAD_CHUNK_SIZE_BYTES=5242880  # 5MB
```

---

## Monitoring & Debugging

### Logs to Watch

```
# Upload initiated
"Upload initiated", session_id=..., user_id=...

# Chunk recorded
"Recorded chunk received", session_id=..., chunk_number=...

# Event published
"Published DocumentUploadedEvent", job_id=..., document_key=...

# Pipeline processing
"Processing document", document_key=..., course_id=...
"Document ingestion complete", document_key=...
```

### Tracking Upload Progress

```
1. Get upload_session_id from initiate_upload response
2. Poll RabbitMQ or logs for DocumentUploadedEvent
3. Track job_id from complete_upload response
4. Monitor pipeline logs for ingestion progress
5. Query vector DB for document embeddings (final confirmation)
```

---

## Testing the Flow

### Manual Testing with curl

```bash
# 1. Initiate upload
curl -X POST http://localhost:8000/v1/documents/initiate-upload \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "document_name": "test.pdf",
    "content_type": "application/pdf",
    "total_size_bytes": 1000000,
    "chunking_strategy": "fixed"
  }'

# Response includes: upload_session_id, presigned_url, chunk_size_bytes

# 2. Upload chunk to MinIO (using presigned_url)
curl -X POST "$PRESIGNED_URL" \
  -F "file=@chunk1.bin"

# 3. Notify chunk received
curl -X POST http://localhost:8000/v1/documents/chunk-received \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "chunk_number": 1,
    "chunk_hash": "abc123",
    "chunk_size_bytes": 1000000
  }'

# 4. Complete upload
curl -X POST http://localhost:8000/v1/documents/complete-upload \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "upload_session_id": "550e8400-e29b-41d4-a716-446655440000",
    "total_chunks": 1,
    "file_hash": "abc123",
    "course_id": "course_123"
  }'
```

---

## Summary

✅ **Complete upload workflow implemented:**
- Client-initiated flow with 3 API steps
- Direct bucket uploads via presigned URLs
- Async pipeline processing via RabbitMQ
- Session management in Redis
- Chunk validation and error handling
- Ready for production deployment

