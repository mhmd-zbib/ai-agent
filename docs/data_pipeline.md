# Data Pipeline
**From raw book to structured, searchable database**
*Course AI Tutor · Doc 1 of 2*

---

## Overview

The pipeline takes a raw book — PDF, EPUB, or DOCX — and transforms it into a hybrid database ready for retrieval. It runs once per course at ingestion time. Every decision here directly affects retrieval quality later. Cheap shortcuts in the pipeline produce bad answers for students.

> **Core Philosophy**
> - Structure first. Understand what every element is before splitting anything.
> - Respect natural boundaries. Never cut a code function, table, or sentence in half.
> - Enrich every chunk. Summary, keywords, and questions make retrieval dramatically better.
> - Store in Postgres, not just a vector DB. You need filtering, joining, and keyword search alongside vectors.

---

## Pipeline at a Glance

```
Raw Book  (PDF / EPUB / DOCX)
      │
      ▼
  Stage 1 ── Document Restructuring
             Document Parser  →  Structure Analyzer
             Output: labeled element tree (headings, paragraphs, code, tables...)
      │
      ▼
  Stage 2 ── Structure-Aware Chunking
             Table Preserver  →  Heading Detector  →  Boundary Detector
             Output: 256–512 token chunks that never split semantic units
      │
      ▼
  Stage 3 ── Metadata Generation
             Summary Generator  →  Keyword Extractor  →  Question Generator
             Output: each chunk enriched with summary, keywords, and questions
      │
      ▼
  Stage 4 ── Hybrid Storage
             Postgres (structured data + pgvector + BM25)
             Output: searchable DB supporting vector, keyword, and filter queries
```

---

## Stage 1 — Document Restructuring

Before any chunking happens, the system must understand what it is looking at. A raw PDF is just bytes. The restructuring stage turns it into a labeled tree — every element classified by type, every heading assigned its level, every code block marked as atomic. Without this step, chunking is blind.

### Components

| Component | Description |
|---|---|
| **Document Parser** | Extracts raw content from the source file. Handles PDF, EPUB, DOCX. Output: raw text, tables, images, code blocks in document order. |
| **Structure Analyzer** | Classifies every extracted element. Detects heading levels, paragraph boundaries, code blocks, tables, lists, figures, and math. Builds a structured tree. |

### Element Classification Rules

| Element | Treatment | Why |
|---|---|---|
| Heading H1/H2/H3 | Hard boundary | Always starts a new chunk. Never split across. |
| Paragraph | Soft boundary | Preferred split point when token limit is reached. |
| Code Block | **Atomic unit** | Never split. One function = one unit, even if long. |
| Table | **Atomic unit** | Serialize to markdown. Keep as one unit. Never split. |
| List | Soft boundary | Split only between items. Never mid-item. |
| Math / Formula | **Atomic unit** | Never split an equation, even across lines. |
| Figure Caption | Sticky | Keep attached to its figure reference. Never orphan. |

### Output — Structured Document Tree

After Stage 1, the book is no longer a flat text file. It is a structured tree you can walk:

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
              "text": "| Case          | Action          |\n| Middle node   | prev.next = ... |" },
            { "type": "paragraph", "text": "Edge cases include deleting the head..." }
          ]
        }
      ]
    }
  ]
}
```

> **⚠️ Recommended Parsers**
> - `docling` — best for academic PDFs and textbooks. Excellent heading and section detection.
> - `unstructured` — best for mixed formats (PDF, EPUB, DOCX, slides, HTML).
> - `pymupdf (fitz)` — fastest. Use as fallback for clean, well-structured PDFs.
> - Never use a parser that only does raw text extraction — you lose all structure.

---

## Stage 2 — Structure-Aware Chunking

Chunking is where most RAG systems get it wrong. They split by token count and call it done. The result is code functions cut in half, tables broken across chunks, and sentences that reference context from the previous chunk. Structure-aware chunking solves all of this.

Target: **256–512 tokens per chunk**. Small enough for precise retrieval, large enough to contain a complete thought. The chunk metadata (Stage 3) compensates for the reduced context window — you do not need 800-token chunks when every chunk has a summary and questions attached.

### Components

| Component | Description |
|---|---|
| **Table Preserver** | Receives table elements from the Structure Analyzer. Wraps each table as a single atomic chunk regardless of its size. Serializes to pipe-delimited markdown for embedding. |
| **Heading Detector** | Monitors the element stream. When a heading is encountered, it always flushes the current chunk and starts a new one. Headings are never embedded inside a chunk — they are always boundaries. |
| **Boundary Detector** | Within a section, accumulates elements until the token budget is reached. Finds the optimal split point: always at a paragraph end, never mid-sentence, never mid-code. |

### Chunking Rules

> **🚫 Hard Rules — Never Violate**
> - Never split a code block. The full function or snippet stays in one chunk.
> - Never split a table. The serialized table is one chunk.
> - Never split mid-sentence. Always end at a sentence boundary.
> - Never cross a heading. A new heading always starts a new chunk.
> - Never cross a section. A chunk belongs to exactly one section.
> - Never cross a chapter. A chunk belongs to exactly one chapter.

> **✅ Soft Rules — Apply Where Possible**
> - Target 256–512 tokens. Go slightly over to preserve a complete thought.
> - Add ~15% token overlap between consecutive chunks in the same section.
> - If a single element exceeds 512 tokens (e.g. a huge table), keep it whole.
> - If a section is under 256 tokens, store it as one chunk with no split.
> - Keep code and the paragraph immediately before it in the same chunk when possible.

### Worked Example — Section 12.3 (Node Deletion)

```
Elements in section 12.3:
  [paragraph]  'To delete a node from the middle...'                 ~180 tokens
  [code]       'def delete_node(prev, target): prev.next = ...'      ~90  tokens
  [paragraph]  'In the case of deleting the head node...'            ~160 tokens
  [table]      '| Case | Pointer Update |...'                        ~220 tokens
  [paragraph]  'Deletion is O(1) given a pointer to prev...'         ~100 tokens

─── Chunker runs ───────────────────────────────────────────────────────────────

chunk_0  →  paragraph[0] + code[0]                                   ~270 tokens
            Kept together: code directly implements the paragraph above it.

chunk_1  →  paragraph[1] + table[0]   (15% overlap from chunk_0 tail) ~420 tokens
            Table kept whole. Slightly over target but correct.

chunk_2  →  paragraph[2]              (15% overlap from chunk_1 tail)  ~140 tokens
            Short but a complete thought. Not merged with chunk_1 (different idea).
```

---

## Stage 3 — Metadata Generation

Every chunk gets three pieces of machine-generated metadata attached at ingestion time. This metadata is what makes retrieval intelligent. You are not just matching text — you are matching intent, terminology, and the questions students actually ask.

> **💡 Why This Changes Everything**
> - A student asks: *"how do I remove something from a linked list?"*
> - The textbook says: *"To delete a node, update the previous node pointer..."*
> - Without question metadata, the embedding similarity is low — different words.
> - With question metadata, the chunk has stored: *"how do I delete a node from a linked list?"*
> - That question matches the student query almost exactly. The right chunk surfaces.

### Components

| Component | Description |
|---|---|
| **Summary Generator** | Generates a 1–2 sentence summary of the chunk. Captures what concept it explains and what a student learns. Used for context enrichment at query time. |
| **Keyword Extractor** | Extracts 3–8 technical terms: function names, data structure names, algorithm names, technical identifiers. Used for BM25 keyword search in Postgres. |
| **Question Generator** | Generates 3–5 questions this chunk would answer, written the way a student would actually type them. Bridges the vocabulary gap between student and textbook. |

### Prompts

#### Summary Generator

```
System:
  "You generate concise summaries of course material chunks for a student AI tutor."

User:
  "Summarize this chunk in 1-2 sentences.
   Focus on what concept it explains and what a student learns from it.
   Be direct. No filler phrases like 'This section discusses...'

   Chapter: {chapter_title}
   Section: {section_title}
   Content types present: {element_types}

   {chunk_text}"
```

#### Keyword Extractor

```
System:
  "You extract technical keywords from course material for search indexing."

User:
  "Extract 3-8 technical keywords from this chunk.
   Include: function names, class names, algorithm names, data structure names,
   technical terms, and key identifiers that appear in the text.
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
   Write them the way a real student types in a chat — informal, sometimes
   imprecise, using everyday language rather than textbook terminology.
   Different questions should cover different angles of the chunk.
   Return a JSON array of strings only. No explanation, no markdown.

   {chunk_text}"
```

### Example Output — chunk_0 of Section 12.3

```json
{
  "chunk_id": "a3f7c...",
  "text": "To delete a node from the middle of a linked list...\ndef delete_node(prev, target): prev.next = target.next",
  "summary": "Explains middle-node deletion in a singly linked list by redirecting the previous node pointer, with Python implementation.",
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

## Stage 4 — Hybrid Storage

The storage layer is a Postgres database with the pgvector extension — not a standalone vector DB. Real queries need more than semantic similarity. They need filtering by course, date, department, and doc type. They need keyword search for exact technical terms. They need joins across tables. Postgres gives you all of this plus vectors in one place.

> **🗄️ Why Postgres, Not Just a Vector DB**
> - Filter by course_id, date, department, doc type — hard to do reliably in a vector DB.
> - Join chunks to courses to departments to enrollment records — SQL handles this natively.
> - BM25 keyword search for exact terms like function names — vectors struggle with this.
> - Transactions, relations, and constraints — you get data integrity for free.
> - pgvector gives you vector similarity inside Postgres. Best of both worlds.

### Schema

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
                   ('textbook','slides','lecture_notes','exercises')),
  chapter        INTEGER,
  chapter_title  TEXT,
  added_at       TIMESTAMPTZ DEFAULT now()
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
  added_at       TIMESTAMPTZ DEFAULT now()
);

-- Required indexes
CREATE INDEX ON chunks (course_id);
CREATE INDEX ON chunks (chapter);
CREATE INDEX ON chunks USING GIN (keywords);
CREATE INDEX ON chunks USING HNSW (embedding vector_cosine_ops);
```

#### summaries
```sql
-- Stores course/chapter/section summaries separately
-- Fetched by metadata filter at query time — no vector search needed
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

### Hybrid Search — Vector + Keyword

Every semantic query runs vector search AND keyword search, then merges results using Reciprocal Rank Fusion (RRF). This handles both vague natural language questions and precise technical queries.

```sql
-- Step 1: BM25 keyword search (exact match on keywords array + text)
SELECT chunk_id,
       ts_rank(to_tsvector('english', text || ' ' || array_to_string(keywords,' ')),
               plainto_tsquery($query)) AS kw_score
FROM chunks
WHERE course_id = $course_id
  AND to_tsvector('english', text || ' ' || array_to_string(keywords,' '))
      @@ plainto_tsquery($query);

-- Step 2: Vector similarity search
SELECT chunk_id,
       1 - (embedding <=> $query_vector) AS vec_score
FROM chunks
WHERE course_id = $course_id
ORDER BY embedding <=> $query_vector
LIMIT 20;

-- Step 3: RRF Fusion
-- final_score = 1/(rank_kw + 60) + 1/(rank_vec + 60)
-- Rank both lists, compute RRF score for each chunk_id, sort descending
-- Take top 6–8 results → pass to RAG pipeline
```

> **🔀 Why RRF Fusion**
> - `'delete_node function'` → keyword search wins (exact identifier match).
> - `'how do I remove something from a linked list?'` → vector search wins (semantic match).
> - RRF merges both lists without needing to normalize differently scaled scores.
> - A chunk appearing in both lists gets a strong RRF score — this is usually your best result.

### Filtering Examples

Things Postgres makes trivial that a standalone vector DB struggles with:

```sql
-- Filter by department (join across tables)
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
```

---

## Ingestion Checklist

Run through this in order every time you onboard a new course. Do not skip steps.

- [ ] Parse the book with a structure-aware library (docling recommended)
- [ ] Run structure analyzer — label every element by type
- [ ] Verify the output tree: check headings are detected, code blocks are marked
- [ ] Run chunker — apply Table Preserver, Heading Detector, Boundary Detector
- [ ] Verify chunks: spot-check 10 chunks — no split code, no split tables, no split sentences
- [ ] Generate summary, keywords, and questions for every chunk (LLM — one batch call)
- [ ] Generate section summaries for every section (LLM)
- [ ] Generate chapter summaries from section summaries (LLM — not raw text)
- [ ] Generate course summary from chapter summaries (LLM — not raw text)
- [ ] Embed all chunks and summaries with the designated embedding model
- [ ] Insert all rows into Postgres with full metadata
- [ ] Verify indexes exist: course_id, GIN on keywords, HNSW on embedding
- [ ] Run validation queries: one concept question, one structural question, one keyword query
- [ ] Confirm course_id filter works — no cross-course leakage