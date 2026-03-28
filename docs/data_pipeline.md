# RAG Data Pipeline
**Production Architecture for Student E-Learning Platforms**
*Course AI Tutor · Engineering Reference · Doc 1 of 2*

---

## Table of Contents

1. [Overview](#1-overview)
2. [Stage 1 — Document Restructuring](#2-stage-1--document-restructuring)
3. [Stage 2 — Structure-Aware Chunking](#3-stage-2--structure-aware-chunking)
4. [Stage 3 — Metadata Generation](#4-stage-3--metadata-generation)
5. [Stage 3b — Hierarchy Summarization](#5-stage-3b--hierarchy-summarization)
6. [Stage 4 — Safety & Quality Gate](#6-stage-4--safety--quality-gate)
7. [Stage 5 — Embedding](#7-stage-5--embedding)
8. [Stage 6 — Hybrid Storage](#8-stage-6--hybrid-storage)
9. [Stage 7 — Observability & Continuous Improvement](#9-stage-7--observability--continuous-improvement)
10. [Ingestion Checklist](#10-ingestion-checklist)
11. [Anti-Patterns to Avoid](#11-anti-patterns-to-avoid)

---

## 1. Overview

This document specifies the production data pipeline for a Retrieval-Augmented Generation (RAG) system deployed on a student e-learning platform. Every design decision below is calibrated to two constraints unique to education: learners ask questions in informal, imprecise language that rarely matches textbook phrasing, and the ground truth source is a fixed corpus where accuracy is non-negotiable.

The pipeline runs **once per course at ingestion time**. Defects introduced here propagate to every student interaction — cheap shortcuts produce bad answers at scale.

### Core Principles

- **Structure first.** Classify every element before splitting anything.
- **Respect semantic boundaries.** Never cut a code function, table, equation, or sentence in half.
- **Enrich every chunk.** Summary, keywords, and student-phrased questions make retrieval dramatically more accurate.
- **Store in Postgres, not just a vector DB.** You need filtering, joins, and keyword search alongside vectors.
- **Observe and iterate.** Log retrievals, measure hit rate, retune thresholds.

### Pipeline at a Glance

```
Raw Book  (PDF / EPUB / DOCX)
      │
      ▼
  Stage 1 ── Document Restructuring
             Parser → Structure Analyzer
             Output: labeled element tree (headings, paragraphs, code, tables…)
      │
      ▼
  Stage 2 ── Structure-Aware Chunking
             Table Preserver → Heading Detector → Boundary Detector
             Output: 256–512 token chunks that never split semantic units
      │
      ▼
  Stage 3 ── Metadata Generation
             Summary Generator → Keyword Extractor → Question Generator
             Output: each chunk enriched with summary, keywords, and questions

  Stage 3b ─ Hierarchy Summarization
             Section → Chapter → Course summaries built bottom-up
      │
      ▼
  Stage 4 ── Safety & Quality Gate
             Validation → Deduplication → PII Scrub
             Output: validated, deduped, PII-free chunks
      │
      ▼
  Stage 5 ── Embedding
             Enriched text → 1536-dim vectors
             Output: one vector per chunk + one per summary
      │
      ▼
  Stage 6 ── Hybrid Storage
             Postgres + pgvector + BM25
             Output: searchable DB supporting vector, keyword, and filter queries
      │
      ▼
  Stage 7 ── Observability
             Retrieval logs → Hit-rate dashboard → Drift alerts
```

| Stage | Name | Input | Output |
|-------|------|-------|--------|
| 1 | Document Restructuring | Raw PDF / EPUB / DOCX | Labeled element tree |
| 2 | Structure-Aware Chunking | Element tree | 256–512 token semantic chunks |
| 3 | Metadata Generation | Raw chunks | Chunks + summary, keywords, questions |
| 3b | Hierarchy Summarization | All section chunks | Section / chapter / course summaries |
| 4 | Safety & Quality Gate | Enriched chunks | Validated, deduped, PII-free chunks |
| 5 | Embedding | Clean chunks | 1536-dim vectors per chunk |
| 6 | Hybrid Storage | Vectors + metadata | Postgres + pgvector + BM25 indexes |
| 7 | Observability | Query logs | Hit-rate dashboard, drift alerts |

---

## 2. Stage 1 — Document Restructuring

Before any chunking happens, the system must understand what it is looking at. A raw PDF is bytes. Stage 1 turns it into a labeled tree — every element classified by type, every heading assigned its level, every code block flagged as atomic. Without this step, chunking is blind.

### 1.1 Parser Selection

| Parser | Best For | Notes |
|--------|----------|-------|
| `docling` | Academic PDFs, textbooks | Best heading detection. Recommended default. |
| `unstructured` | Mixed formats (EPUB, DOCX, slides, HTML) | Handles format diversity well. |
| `pymupdf (fitz)` | Clean, well-structured PDFs | Fastest. Use as fallback only. |
| `marker` | Complex multi-column layouts | Good for dense scientific papers. |

> **🚫 Never do this**
> - Do not use a parser that only extracts raw text — you lose all structure and Stage 2 cannot function.
> - Do not skip parser validation. Always spot-check 5–10 pages to confirm headings, code blocks, and tables are detected correctly.

### 1.2 Element Classification Rules

| Element | Treatment | Reason |
|---------|-----------|--------|
| Heading H1 / H2 / H3 | Hard boundary | Always starts a new chunk. Never split across. |
| Paragraph | Soft boundary | Preferred split point when token budget is reached. |
| Code block | **Atomic unit — never split** | One function = one unit. Students need working code. |
| Table | **Atomic unit — serialize to markdown** | A broken table is unreadable and unembeddable. |
| List | Soft boundary | Split only between items. Never mid-item. |
| Math / Formula | **Atomic unit — never split** | Broken equations are meaningless. |
| Figure caption | Sticky — keep with figure ref | Orphaned captions confuse the retriever. |
| Admonition / callout | Treat as paragraph | Preserve note/warning/tip prefix in text. |

### 1.3 Structured Document Tree Output

After Stage 1 the book is a structured tree you can walk. Every downstream stage reads from this tree, not from raw file bytes.

```json
{
  "course_id": "CS101",
  "source_type": "textbook",
  "chapters": [
    {
      "chapter": 12,
      "title": "Linked Lists",
      "sections": [
        {
          "section": 3,
          "title": "Node Deletion",
          "elements": [
            { "type": "paragraph", "text": "To delete a node from the middle..." },
            { "type": "code", "lang": "python",
              "text": "def delete_node(prev, target):\n  prev.next = target.next" },
            { "type": "table",
              "text": "| Case | Action |\n|------|--------|\n| Middle | prev.next = target.next |" },
            { "type": "paragraph", "text": "Edge cases include deleting the head..." }
          ]
        }
      ]
    }
  ]
}
```

---

## 3. Stage 2 — Structure-Aware Chunking

Chunking is where most RAG systems fail. Splitting by token count alone produces code functions cut in half, tables broken across chunks, and sentences that reference context from the previous chunk. Structure-aware chunking solves all of this by reading the element tree from Stage 1.

**Target: 256–512 tokens per chunk.** Small enough for precise retrieval, large enough to contain a complete thought. The Stage 3 metadata (summary + questions) compensates for the narrower context window — you do not need 800-token chunks when every chunk carries semantic enrichment.

### 2.1 Components

| Component | Description |
|-----------|-------------|
| **Table Preserver** | Receives table elements from the element tree. Wraps each as a single atomic chunk regardless of size. Serializes to pipe-delimited markdown for embedding. |
| **Heading Detector** | Monitors the element stream. A new heading always flushes the current chunk and starts a new one. Headings are never embedded inside a chunk. |
| **Boundary Detector** | Within a section, accumulates elements until the token budget is reached. Finds the optimal split: always at a paragraph end, never mid-sentence, never mid-code. |

### 2.2 Hard and Soft Rules

> **🚫 Hard Rules — Never Violate**
> - Never split a code block. The full function stays in one chunk.
> - Never split a table. The serialized table is one chunk.
> - Never split mid-sentence. Always end at a sentence boundary.
> - Never cross a heading. A new heading always starts a new chunk.
> - Never cross a section. A chunk belongs to exactly one section.
> - Never cross a chapter. A chunk belongs to exactly one chapter.

> **✅ Soft Rules — Apply Where Possible**
> - Target 256–512 tokens. Go slightly over to preserve a complete thought.
> - Add ~15% token overlap between consecutive chunks in the same section.
> - If a single element exceeds 512 tokens (e.g. huge table), keep it whole regardless.
> - If a section is under 256 tokens, store it as one chunk — do not split.
> - Keep a code block and the paragraph immediately before it in the same chunk when possible.
> - For very long code blocks (>512 tokens), annotate the chunk as code-only with a linking summary.

### 2.3 Worked Example — Section 12.3 Node Deletion

```
Elements in section 12.3:
  [paragraph]  'To delete a node from the middle...'                  ~180 tokens
  [code]       'def delete_node(prev, target): prev.next = ...'       ~90  tokens
  [paragraph]  'In the case of deleting the head node...'             ~160 tokens
  [table]      '| Case | Pointer Update |...'                         ~220 tokens
  [paragraph]  'Deletion is O(1) given a pointer to prev...'          ~100 tokens

── Chunker output ──────────────────────────────────────────────────────────────

chunk_0  →  paragraph[0] + code[0]                                    ~270 tokens
            Kept together: code directly implements the paragraph.

chunk_1  →  paragraph[1] + table[0]   (15% overlap from chunk_0 tail) ~420 tokens
            Table kept whole. Slightly over target but semantically correct.

chunk_2  →  paragraph[2]              (15% overlap from chunk_1 tail)  ~140 tokens
            Short but complete thought. Not merged — different concept.
```

---

## 4. Stage 3 — Metadata Generation

Every chunk gets three pieces of LLM-generated metadata attached at ingestion time. This metadata is what makes retrieval intelligent. You are not just matching text — you are matching intent, vocabulary, and the questions real students actually type.

> **💡 Why This Changes Retrieval**
> - Student asks: *"how do I remove something from a linked list?"*
> - Textbook says: *"To delete a node, update the previous node pointer..."*
> - Without question metadata: embedding similarity is low — different vocabulary.
> - With question metadata: the chunk stores *"how do I delete a node from a linked list?"* — near-exact match.
> - The right chunk surfaces. The wrong answer never reaches the student.

### 3.1 Components

| Component | Output | Used For |
|-----------|--------|----------|
| **Summary Generator** | 1–2 sentence summary per chunk | Context enrichment at query time; chain-of-thought prompting |
| **Keyword Extractor** | 3–8 technical terms per chunk | BM25 keyword index in Postgres; exact-match retrieval |
| **Question Generator** | 3–5 student-phrased questions per chunk | Bridges vocabulary gap between learner and textbook |

### 3.2 Prompts

#### Summary Generator

```
System:
  "You generate concise summaries of course material for a student AI tutor."

User:
  "Summarize this chunk in 1-2 sentences.
   Focus on what concept it explains and what a student learns from it.
   Be direct. No filler like 'This section discusses...'

   Chapter: {chapter_title}
   Section: {section_title}
   Content types: {element_types}

   {chunk_text}"
```

#### Keyword Extractor

```
System:
  "You extract technical keywords from course material for search indexing."

User:
  "Extract 3-8 technical keywords from this chunk.
   Include: function names, class names, algorithm names, data structure names,
   and key identifiers that appear in the text.
   Prioritize specific terms over generic ones.
   Return a JSON array of strings only. No explanation, no markdown.

   {chunk_text}"
```

#### Question Generator

```
System:
  "You generate student questions that course material chunks answer."

User:
  "Generate 3-5 questions a student might ask that this chunk answers.
   Write them how a real student types in chat — informal, sometimes imprecise,
   using everyday language rather than textbook terminology.
   Different questions should cover different angles of the chunk.
   Return a JSON array of strings only. No explanation, no markdown.

   {chunk_text}"
```

### 3.3 Example Output — chunk_0 of Section 12.3

```json
{
  "chunk_id": "a3f7c...",
  "text": "To delete a node from the middle of a linked list...\ndef delete_node(prev, target): prev.next = target.next",
  "summary": "Explains middle-node deletion in a singly linked list by redirecting the previous node pointer, with a Python implementation.",
  "keywords": ["linked list", "node deletion", "prev.next", "delete_node", "singly linked list", "pointer manipulation"],
  "questions": [
    "how do I delete a node from a linked list?",
    "what happens to the pointer when you delete a node?",
    "can you show me the code for deleting a node?",
    "how does prev.next work when removing an element?",
    "what is the delete_node function?"
  ]
}
```

---

## 5. Stage 3b — Hierarchy Summarization

After all chunks are enriched, generate summaries at three hierarchy levels. These are stored in the `summaries` table and fetched by metadata filter at query time — no vector search needed for structural navigation.

| Level | Input | Method | Use Case |
|-------|-------|--------|----------|
| Section | All chunks in the section | LLM synthesis of chunk summaries | Answer "what does section X cover?" |
| Chapter | All section summaries | LLM synthesis — **not raw text** | Chapter overview, navigation |
| Course | All chapter summaries | LLM synthesis — **not raw text** | Course intro, prerequisite check |

> **📐 Hierarchy Rule**
> - Always build summaries bottom-up: chunks → sections → chapters → course.
> - Never summarize a chapter directly from raw text — always from section summaries.
> - This keeps token usage manageable and produces more coherent higher-level summaries.

---

## 6. Stage 4 — Safety & Quality Gate

Every chunk passes through a quality gate before embedding. This stage exists because LLM-generated metadata occasionally drifts, parsers occasionally hallucinate structure, and student platforms have strict data-safety obligations. A bad chunk that clears the gate produces bad answers indefinitely.

### 4.1 Validation Checks

| Check | Threshold / Rule | Action on Failure |
|-------|-----------------|-------------------|
| Token count | 50 ≤ tokens ≤ 600 | Re-chunk or flag for manual review |
| Summary present | Non-empty string | Re-run Summary Generator |
| Keywords present | ≥ 3 terms | Re-run Keyword Extractor |
| Questions present | ≥ 3 items | Re-run Question Generator |
| No split code block | Must not start/end mid-function | Re-chunk the section |
| No split table | Must not start/end mid-row | Re-chunk the section |
| No broken sentence | Must end at sentence boundary | Trim to last full sentence |
| PII detection | No student names, emails, IDs in source | Redact or reject chunk |
| Duplicate detection | Cosine similarity < 0.97 vs existing chunks | Deduplicate; keep most recent |
| Source integrity | `course_id` + `doc_id` present and valid | Reject; log and alert |

### 4.2 PII Policy for Education Platforms

Student platforms in most jurisdictions are subject to FERPA (US), GDPR (EU), or equivalent regulations. The source corpus should never contain student PII, but parsers occasionally extract metadata headers containing author emails or student IDs from document properties.

- Run a regex pass for email addresses, phone numbers, and national ID patterns before embedding.
- Strip document metadata fields (`author`, `last-modified-by`) from the structured tree before Stage 2.
- Log all PII detections to a separate audit table — do not store them in the chunks table.
- If PII is found in the body text of a chunk, reject and escalate — do not attempt auto-redaction.

---

## 7. Stage 5 — Embedding

Embedding converts text chunks and their metadata into dense vectors encoding semantic meaning. The embedding model is the single most important external dependency in the pipeline — changing it requires re-embedding everything.

### 5.1 What to Embed

| Field | Embed? | Why |
|-------|--------|-----|
| `chunk.text` | Yes — always | Core semantic content |
| `chunk.summary` | Concatenate with text | Adds context; improves retrieval precision |
| `chunk.questions` | Concatenate with text | Bridges student vocabulary to textbook language |
| `chunk.keywords` | Concatenate with text | Boosts exact-match recall |
| `summaries.text` (section/chapter) | Yes — separately | Enables structural navigation at query time |
| `chunk.keywords` alone | No | Sparse features; use BM25 index instead |

> **🔢 Embedding Strategy**
>
> Embed the following enriched string per chunk:
> ```
> {chunk.text}
>
> {summary}
>
> {questions joined by space}  {keywords joined by space}
> ```
> At query time, embed **only the raw student query** — do not add metadata to the query string.
>
> **Model recommendations:**
> - `text-embedding-3-small` (OpenAI, 1536-dim) — recommended default
> - `mxbai-embed-large` (open-source alternative)
>
> **Hard rule:** Never mix embedding model versions across a corpus. Pin the model version and re-embed everything on model changes.

---

## 8. Stage 6 — Hybrid Storage

The storage layer is Postgres with the pgvector extension — not a standalone vector DB. Real queries on an education platform need filtering by course, cohort, and document type; keyword search for exact function names; and joins across enrollment records. Postgres gives you all of this plus vectors in one place.

> **🗄️ Why Postgres, Not Just a Vector DB**
> - Filter by `course_id`, date, department, doc type — hard to do reliably in a vector DB.
> - Join chunks to courses to departments to enrollment records — SQL handles this natively.
> - BM25 keyword search for exact terms like function names — vectors struggle with this.
> - Transactions, relations, and constraints — data integrity for free.
> - pgvector gives you vector similarity inside Postgres. Best of both worlds.

### 6.1 Schema

#### courses
```sql
CREATE TABLE courses (
  course_id      TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  department     TEXT,
  created_at     TIMESTAMPTZ DEFAULT now(),
  prerequisites  TEXT[]
);
```

#### documents
```sql
CREATE TABLE documents (
  doc_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id      TEXT REFERENCES courses(course_id),
  title          TEXT,
  source_type    TEXT CHECK (source_type IN
                   ('textbook','slides','lecture_notes','exercises','past_papers')),
  chapter        INTEGER,
  chapter_title  TEXT,
  version        INTEGER DEFAULT 1,
  added_at       TIMESTAMPTZ DEFAULT now(),
  is_active      BOOLEAN DEFAULT TRUE
);
```

#### chunks
```sql
CREATE TABLE chunks (
  chunk_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id         UUID REFERENCES documents(doc_id),
  course_id      TEXT REFERENCES courses(course_id),
  chapter        INTEGER,
  chapter_title  TEXT,
  section        INTEGER,
  section_title  TEXT,
  chunk_index    INTEGER,
  element_types  TEXT[],          -- ['paragraph','code'] etc.
  text           TEXT NOT NULL,
  summary        TEXT,
  keywords       TEXT[],
  questions      TEXT[],
  token_count    INTEGER,
  embedding      vector(1536),    -- pgvector
  quality_score  REAL,            -- 0.0–1.0 from validation gate
  added_at       TIMESTAMPTZ DEFAULT now(),
  is_active      BOOLEAN DEFAULT TRUE
);

-- Required indexes
CREATE INDEX ON chunks (course_id);
CREATE INDEX ON chunks (chapter);
CREATE INDEX ON chunks (is_active);
CREATE INDEX ON chunks USING GIN (keywords);
CREATE INDEX ON chunks USING HNSW (embedding vector_cosine_ops);
-- Optional: full-text search on chunk text
CREATE INDEX ON chunks USING GIN (to_tsvector('english', text));
```

#### summaries
```sql
CREATE TABLE summaries (
  summary_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id      TEXT REFERENCES courses(course_id),
  level          TEXT CHECK (level IN ('course','chapter','section')),
  chapter        INTEGER,
  chapter_title  TEXT,
  section        INTEGER,
  section_title  TEXT,
  text           TEXT NOT NULL,
  embedding      vector(1536)
);
```

#### retrieval_log
```sql
CREATE TABLE retrieval_log (
  log_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id     UUID,
  course_id      TEXT,
  query_text     TEXT,
  retrieved_ids  UUID[],
  top_score      REAL,
  method         TEXT,            -- 'vector', 'keyword', 'hybrid'
  latency_ms     INTEGER,
  created_at     TIMESTAMPTZ DEFAULT now()
);
```

### 6.2 Hybrid Search — Vector + BM25 + RRF

Every semantic query runs vector search AND keyword search in parallel, then merges results using Reciprocal Rank Fusion (RRF). This handles both vague natural language questions and precise technical queries without needing to tune score normalization.

```sql
-- Step 1: BM25 keyword search
SELECT chunk_id,
       ts_rank(to_tsvector('english', text || ' ' || array_to_string(keywords,' ')),
               plainto_tsquery($query)) AS kw_score
FROM chunks
WHERE course_id = $course_id
  AND is_active = TRUE
  AND to_tsvector('english', text || ' ' || array_to_string(keywords,' '))
      @@ plainto_tsquery($query)
ORDER BY kw_score DESC LIMIT 20;

-- Step 2: Vector similarity search
SELECT chunk_id,
       1 - (embedding <=> $query_vector) AS vec_score
FROM chunks
WHERE course_id = $course_id
  AND is_active = TRUE
ORDER BY embedding <=> $query_vector
LIMIT 20;

-- Step 3: RRF Fusion
-- final_score = 1/(rank_kw + 60) + 1/(rank_vec + 60)
-- A chunk appearing in both lists gets a strong combined score.
-- Take top 6–8 results → pass to LLM answer generator.
```

| Query Type | Dominant Method | Example |
|------------|----------------|---------|
| Informal / natural language | Vector search wins | *"how do I remove something from a list?"* |
| Exact technical term | Keyword search wins | *"delete_node function python"* |
| Both signals present | RRF top result | Appears in both result sets → highest confidence |

> **🔀 Why RRF Fusion**
> - `'delete_node function'` → keyword search wins (exact identifier match).
> - `'how do I remove something from a linked list?'` → vector search wins (semantic match).
> - RRF merges both lists without needing to normalize differently scaled scores.
> - A chunk appearing in both lists gets a strong RRF score — this is usually your best result.

### 6.3 Filtering Examples

```sql
-- Filter by department
SELECT c.* FROM chunks c
JOIN courses co ON c.course_id = co.course_id
WHERE co.department = 'Computer Science';

-- Filter by date (content added this semester only)
SELECT * FROM chunks
WHERE course_id = 'CS101'
  AND added_at >= '2024-09-01';

-- Filter by doc type
SELECT c.* FROM chunks c
JOIN documents d ON c.doc_id = d.doc_id
WHERE c.course_id = 'CS101'
  AND d.source_type = 'lecture_notes';

-- Filter to active chunks only (post content update)
SELECT * FROM chunks
WHERE course_id = 'CS101'
  AND is_active = TRUE;
```

---

## 9. Stage 7 — Observability & Continuous Improvement

A pipeline with no feedback loop degrades silently. As courses are updated and student question patterns shift, retrieval quality drifts. Stage 7 instruments the retrieval path and surfaces degradation before it affects student outcomes.

### 7.1 Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| Retrieval hit rate | > 85% of queries return ≥ 1 relevant chunk | < 75% over 24 hours |
| Top-1 cosine similarity | > 0.72 average | < 0.60 over 100 queries |
| Answer rejection rate | < 5% of LLM answers rejected as off-topic | > 10% over 24 hours |
| Latency p95 | < 800ms end-to-end retrieval | > 1500ms |
| Chunk coverage | ≥ 95% of questions resolve to a chunk | < 90% (gap in corpus) |

### 7.2 When to Re-Ingest

- A new edition of the textbook is adopted.
- Hit rate drops below 75% after a curriculum change.
- The embedding model version is updated (forces full re-embed).
- More than 20% of a chapter's content is revised.
- A new source type (e.g. past exam papers) is added to the corpus.

---

## 10. Ingestion Checklist

Run through this in order every time you onboard a new course. Do not skip steps.

### Stage 1 — Document Restructuring
- [ ] Parse the book with a structure-aware library (`docling` recommended).
- [ ] Strip document metadata (`author`, `last-modified-by`) from the tree.
- [ ] Run structure analyzer — label every element by type.
- [ ] Spot-check output tree: confirm headings, code blocks, and tables are detected correctly.
- [ ] Verify no PII in document body text. Reject and escalate if found.

### Stage 2 — Chunking
- [ ] Run chunker — apply Table Preserver, Heading Detector, Boundary Detector.
- [ ] Spot-check 10 chunks: no split code, no split tables, no split sentences.
- [ ] Confirm token counts are within 50–600 range for all chunks.
- [ ] Confirm 15% overlap is applied between consecutive chunks in the same section.

### Stage 3 — Metadata Generation
- [ ] Generate summary, keywords, and questions for every chunk (LLM batch call).
- [ ] Generate section summaries for every section (LLM).
- [ ] Generate chapter summaries from section summaries, not raw text (LLM).
- [ ] Generate course summary from chapter summaries (LLM).

### Stage 4 — Quality Gate
- [ ] Run all validation checks (token count, PII, completeness, no split elements).
- [ ] Run duplicate detection — reject chunks with cosine similarity > 0.97 vs existing.
- [ ] Review any flagged chunks manually before proceeding.

### Stage 5 — Embedding
- [ ] Embed enriched string: `text + summary + questions + keywords`.
- [ ] Confirm embedding model version matches the version used for existing chunks.

### Stage 6 — Storage
- [ ] Insert all chunks and summaries into Postgres with full metadata.
- [ ] Verify indexes exist: `course_id`, `is_active`, GIN on `keywords`, HNSW on `embedding`.
- [ ] Run validation queries: one concept question, one structural question, one keyword query.
- [ ] Confirm `course_id` filter works — no cross-course result leakage.

### Stage 7 — Observability
- [ ] Confirm `retrieval_log` table is capturing queries.
- [ ] Baseline the hit-rate metric for the new course.
- [ ] Set alert thresholds in your monitoring dashboard.

---

## 11. Anti-Patterns to Avoid

| Anti-Pattern | Problem | Correct Approach |
|--------------|---------|-----------------|
| Chunking by character/token count only | Splits code, tables, and sentences — retrieval returns broken context | Use structure-aware chunking from the Stage 1 element tree |
| Using only vector search | Fails on exact technical terms like function names | Always combine with BM25 keyword search via RRF |
| Skipping metadata generation | Student vocabulary never matches textbook text | Generate summary + questions for every chunk |
| Using a standalone vector DB | No filtering by course, joins to enrollment, or BM25 | Use Postgres + pgvector as the single store |
| One giant chunk per section | Retrieval is imprecise; wrong paragraph surfaces with correct section | 256–512 token chunks with 15% overlap |
| Building chapter summaries from raw text | Too long, loses coherence, hits token limits | Summarize bottom-up: chunks → sections → chapters |
| No quality gate | Bad chunks silently degrade every student interaction | Validate every chunk before embedding |
| Mixing embedding model versions | Similarity scores become meaningless across the corpus | Pin model version; re-embed all on model change |
| No observability | Quality drift goes undetected until students complain | Log every retrieval; alert on hit-rate drop |

---

*RAG Data Pipeline · Production Reference · Doc 1 of 2*