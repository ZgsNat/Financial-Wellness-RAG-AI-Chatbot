# Phase 2 — RAG Pipeline: Implementation Reference

> **Audience:** Developer working on this codebase after me, or yourself returning after a break.  
> **Covers:** What was built, why each piece exists, the full data flow, and how to test it.

---

## 1. What Problem Phase 2 Solves

Phase 1 already stores transactions and journal entries and generates **rule-based** insight text like:
> "You spent 750,000 VND on shopping."

That is just a reflection of raw data — not an *insight*.

Phase 2 adds a **Personal Context Engine** that can answer questions like:
> "Tại sao dạo này tôi tiêu nhiều hơn?"  
> "Khi nào tôi có xu hướng mua sắm?"  
> "Tôi cảm thấy thế nào sau những lần chi tiêu lớn?"

These questions require **narrative context** — the content of journal entries, mood notes, and transaction descriptions in relation to each other. SQL aggregation cannot answer them. RAG can.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        INGESTION PATH                           │
│                                                                 │
│  transaction-service ──RabbitMQ──► insight-service consumer     │
│  journal-service     ──RabbitMQ──► insight-service consumer     │
│                                         │                       │
│                              asyncio.create_task()              │
│                                         │                       │
│                                    ingest_document()            │
│                                    ┌────┴────────────────────┐  │
│                                    │ 1. format document text  │  │
│                                    │ 2. chunk (recursive)     │  │
│                                    │ 3. POST /embed           │  │
│                                    │    embedding-service     │  │
│                                    │ 4. upsert document_chunks│  │
│                                    │    ON CONFLICT DO UPDATE │  │
│                                    └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         QUERY PATH                              │
│                                                                 │
│  User ──POST /insights/chat──► Kong (JWT + rate limit 10/min)   │
│                                    │                            │
│                             insight-service                     │
│                             ┌──────┴──────────────────────────┐ │
│                             │ 1. embed question               │ │
│                             │    POST embedding-service/embed  │ │
│                             │ 2. vector search document_chunks │ │
│                             │    WHERE user_id = ?            │ │  ← multi-tenant isolation
│                             │    ORDER BY embedding <=> ?     │ │
│                             │    LIMIT 8                      │ │
│                             │ 3. build context string         │ │
│                             │ 4. call Gemini Flash 2.5        │ │
│                             │    stream=True                  │ │
│                             │ 5. yield SSE deltas             │ │
│                             └─────────────────────────────────┘ │
│                                    │                            │
│  User ◄── SSE stream ──────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. New Services and Files

### 3.1 embedding-service (NEW)

**Location:** `backend/services/embedding/`

**Purpose:**  
Runs `BAAI/bge-m3` (~2.2 GB model) as a dedicated microservice. Separated from insight-service so:
- Model loads only once, in one container
- insight-service stays lightweight
- Model can be swapped (BGE-M3 → another) without touching pipeline logic

**File structure:**
```
services/embedding/
  Dockerfile                  ← pre-downloads BGE-M3 into image layer at build time
  pyproject.toml
  src/embedding/
    __init__.py
    config.py                 ← Settings (model_name)
    model.py                  ← BGE-M3 singleton: load_model() + get_model()
    main.py                   ← FastAPI app, /health + lifespan that calls load_model()
    routers/
      __init__.py
      embed.py                ← POST /embed endpoint
```

**API:**

```
POST /embed
Content-Type: application/json

{
  "texts": ["string", ...],
  "mode": "query" | "passage"     ← BGE prefix applied internally
}

→ 200 OK
{
  "embeddings": [[0.1, 0.2, ...], ...],   ← float[1024] per text
  "model": "BAAI/bge-m3",
  "dimension": 1024
}

GET /health
→ { "status": "ok", "model_loaded": true }
```

**BGE-M3 prefix trick (important):**

BGE-M3 performs significantly better when given instruction prefixes:
- `"query: {user question}"` — when embedding a search query
- `"passage: {document text}"` — when embedding document chunks to store

The `embed.py` router applies these prefixes automatically based on the `mode` field.

---

### 3.2 insight-service additions

#### 3.2.1 New: `rag/` package

```
src/insight/rag/
  __init__.py
  chunker.py          ← recursive/structural text chunking
  ingestion.py        ← format + chunk + embed + upsert pipeline
  retrieval.py        ← pgvector cosine similarity search
  context_builder.py  ← dedup, format, truncate retrieved chunks
  llm_client.py       ← Gemini Flash 2.5 streaming
  prompt.py           ← system prompt template + builder
```

#### 3.2.2 New: `models/chunk.py`

`DocumentChunk` SQLAlchemy model for the `document_chunks` table.

Key columns:
| Column | Type | Purpose |
|---|---|---|
| `user_id` | UUID | Multi-tenant isolation — **always filtered first** |
| `source_type` | TEXT | `'transaction'` \| `'journal_entry'` \| `'mood_entry'` |
| `source_id` | UUID | Points back to source record (no real FK — cross-DB) |
| `chunk_index` | INT | Position within source document (0-based) |
| `content` | TEXT | Formatted document text that was embedded |
| `embedding` | vector(1024) | BGE-M3 output — requires pgvector extension |
| `metadata` | JSONB | Structured fields for optional SQL pre-filtering |

Unique constraint on `(source_id, chunk_index)` → upserts are idempotent.

#### 3.2.3 New: `routers/chat.py`

`POST /insights/chat` — SSE streaming endpoint.

```python
# Request
{ "question": "Tại sao tôi hay mua đồ khi stress?", "stream": true }

# Response (Content-Type: text/event-stream)
data: {"delta": "Dựa trên "}
data: {"delta": "lịch sử của bạn..."}
...
data: {"done": true, "sources": [{"source_type": "transaction", "source_id": "...", "similarity": 0.87}]}
```

#### 3.2.4 New: migration `0002_document_chunks.py`

Creates `document_chunks` table with:
- `vector(1024)` column (pgvector type, requires `pgvector/pgvector:pg16` image)
- HNSW index for real-time cosine similarity search
- Composite index on `(user_id, source_type)` for pre-filtering

---

## 4. Data Flow in Detail

### 4.1 Ingestion Flow (when user creates a transaction or journal entry)

```
1. User POSTs to /transactions or /journal/entries
2. transaction-service / journal-service publishes event to RabbitMQ
3. insight-service consumer receives the event
4. Consumer calls InsightService.refresh_spending_insight() or refresh_mood_insight()
   └─ This is Phase 1 behavior — persists rule-based insight text (unchanged)
5. Consumer calls asyncio.create_task(ingest_document(...))
   └─ This is Phase 2 — fires NON-BLOCKING task:
      a. Format document text (see section 4.2)
      b. Chunk via chunk_text() (see section 4.3)
      c. POST all chunks to embedding-service /embed { mode: "passage" }
      d. Receive List[List[float]] embeddings
      e. INSERT INTO document_chunks ... ON CONFLICT DO UPDATE
6. Consumer ACKs the RabbitMQ message
   └─ Step 5 does NOT block this ACK — if embedding-service is slow or down,
      the insight phase 1 still works. Ingestion failures are logged only.
```

### 4.2 Document Format (critical for retrieval quality)

Different source types need different formatting because what matters for retrieval differs:

**Transaction:**
```
# Includes date + type + amount + category in text
# so vector search can find "shopping expenses in April"
# even without SQL filters

"2026-04-08: expense 750,000 VND [shopping]
Mua mô hình sau buổi phỏng vấn căng thẳng"

# metadata JSONB:
{ "category": "shopping", "amount": "750000", "currency": "VND",
  "transaction_date": "2026-04-08", "type": "expense" }
```

**Journal entry (chunked):**
```
# Header prefix on every chunk so model knows the date
# even for overlap chunks that don't start at the beginning

"[Journal 2026-04-08]
Hôm nay mình stress vì deadline dự án. Cuối cùng lại lên Shopee..."

# metadata JSONB:
{ "word_count": 120, "created_at": "2026-04-08T..." }
```

**Mood entry:**
```
# Score is embedded AS TEXT so user can ask "when was I at score 2?"
# and it will match semantically

"[Mood 2026-04-08] Score: 2/5
Cảm thấy mệt mỏi và áp lực"

# metadata JSONB:
{ "score": "2", "created_at": "2026-04-08T..." }
```

> **Why embed metadata as text?** If you only embed `"Mua mô hình"`, the vector carries no date or category information. A user query about "April shopping" would not match it. By embedding the full formatted string, all metadata participates in the semantic similarity computation.

### 4.3 Chunking Strategy

```
chunk_text(text, chunk_size=512, overlap=64)

Step 1: Split by "\n\n" (paragraph boundaries)
Step 2: If a paragraph > 512 tokens: split further by ". " (sentences)
Step 3: Merge small segments up to 512-token limit
Step 4: Carry 64-token overlap between consecutive chunks
        so context is not lost at chunk boundaries
```

Token count is approximated as `len(text.split()) * 1.3` — no real tokenizer needed at this data scale.

Transactions and mood entries are short — they become exactly **1 chunk** each.  
Journal entries may be split into **multiple chunks** with overlap.

### 4.4 Query Flow (when user sends a chat message)

```
1. User POSTs { "question": "...", "stream": true } to /insights/chat
2. Kong: JWT validation + rate limit (10 req/min) → routes to insight-service
3. chat.py router opens SSE stream:
   a. _embed_query(question)
      → POST embedding-service /embed { texts: [question], mode: "query" }
      → Returns float[1024] query vector
   b. retrieve_chunks(db, user_id, query_vector, top_k=8)
      → SQL: SELECT ... FROM document_chunks
              WHERE user_id = $user_id         ← ALWAYS first
                AND embedding IS NOT NULL
              ORDER BY embedding <=> $query_vector
              LIMIT 8
      → Returns List[RetrievedChunk] sorted by similarity (desc)
   c. build_context(chunks)
      → Dedup: skip near-duplicate chunks (similarity > 0.97 same source_id)
      → Format: "Source [transaction]: 2026-04-08: expense 750,000 VND..."
      → Truncate: stop adding chunks when total > 6000 tokens
      → Returns (context_string, sources_list)
   d. stream_llm(context, question)
      → Gemini Flash 2.5 with streaming=True
      → System prompt injects context + today's date + persona
      → Yield text deltas
   e. SSE: yield data: {"delta": "..."} for each LLM chunk
      On finish: yield data: {"done": true, "sources": [...]}
```

---

## 5. Why These Technical Choices

### Why BGE-M3?
- Multilingual SOTA (Vietnamese works well)
- Dense + sparse hybrid search support
- 1024 dimension output (good quality/size balance)
- Open-source, runs on CPU (no GPU needed for demo)
- `normalize_embeddings=True` → cosine similarity = dot product → works directly with pgvector `<=>` operator

### Why pgvector (not Pinecone/Weaviate)?
- Already have PostgreSQL running
- No extra infrastructure
- SQL filters (`WHERE user_id = ?`) are native — no reimplementation
- HNSW index supports real-time inserts (unlike IVFFlat which needs training data first)

### Why HNSW index (not IVFFlat)?
- IVFFlat requires a training phase with enough existing data
- HNSW builds incrementally — works from the first insert
- Real-time event-driven ingestion requires this behavior

### Why Gemini Flash 2.5 (not GPT-4)?
- Free tier: 15 RPM, 1M tokens/day — enough for dev/demo
- Fast — "Flash" variant optimized for speed
- `google-generativeai` SDK has native `generate_content_async(stream=True)`
- Easy swap to Pro/GPT-4 later — only `llm_client.py` changes

### Why SSE (not WebSocket)?
- Stateless — no persistent connection management
- Works over standard HTTP/2
- Simple to implement and consume in any frontend
- Sufficient for one-way streaming (LLM → client)

### Why fire-and-forget ingestion?
- Embedding BGE-M3 on CPU can take 1–3 seconds per batch
- If ingestion blocked the RabbitMQ consumer ACK, slow embedding would cause message redelivery
- `asyncio.create_task()` runs ingestion concurrently — consumer ACKs immediately
- Ingestion failure → logged, not re-raised; Phase 1 insight still works

---

## 6. Multi-Tenant Security

**This is critical.** The `document_chunks` table stores data for ALL users.

Every retrieval query has a mandatory `WHERE user_id = $user_id` clause **before** the vector similarity computation. Without this, User A's query could retrieve User B's journal entries.

The `user_id` comes from the JWT sub claim, injected by Kong via `X-Authenticated-Userid` header after JWT verification. `dependencies.py` extracts it.

The HNSW index does not support pre-filtering natively, so the query structure is:
```sql
-- Filter user first, then rank by similarity
WHERE user_id = $user_id
  AND embedding IS NOT NULL
ORDER BY embedding <=> $query_vector
LIMIT 8
```

This performs a post-filter scan over only that user's chunks, which is correct and safe.

---

## 7. Modified Files Summary

| File | Change |
|---|---|
| `backend/.env` | Replaced `ANTHROPIC_API_KEY=` with `GEMINI_API_KEY=` |
| `backend/docker-compose.yaml` | Added `embedding` service; updated `insight` env vars |
| `backend/kong/kong.yml` | Added `POST /insights/chat` route (10 req/min limit) |
| `insight/config.py` | New settings: `embedding_service_url`, `gemini_api_key`, `gemini_model`, `rag_*` |
| `insight/pyproject.toml` | Replaced `anthropic>=0.28.0` with `google-generativeai>=0.8.0` |
| `insight/messaging/consumers.py` | Added `asyncio.create_task(ingest_document(...))` in both consumers |
| `insight/main.py` | Registered `chat_router` |
| `insight/migrations/versions/0002_document_chunks.py` | **New**: creates table + HNSW index |
| `insight/models/chunk.py` | **New**: `DocumentChunk` SQLAlchemy model |
| `insight/rag/__init__.py` | **New**: package marker |
| `insight/rag/chunker.py` | **New**: recursive text chunking |
| `insight/rag/ingestion.py` | **New**: format + chunk + embed + upsert pipeline |
| `insight/rag/retrieval.py` | **New**: pgvector cosine similarity search |
| `insight/rag/context_builder.py` | **New**: dedup, format, truncate |
| `insight/rag/llm_client.py` | **New**: Gemini streaming client |
| `insight/rag/prompt.py` | **New**: system prompt template |
| `insight/routers/chat.py` | **New**: SSE chat endpoint |

---

## 8. Setup Before Running

### Step 1: Get Gemini API key
1. Go to https://aistudio.google.com
2. Click **"Get API key"** → **"Create API key"**
3. Copy the key

### Step 2: Add to `.env`
```
# backend/.env
GEMINI_API_KEY=AIzaSy...your_key_here
```

### Step 3: Build and start
```bash
cd backend

# First build will take 10–15 minutes (BGE-M3 ~2.2 GB downloads into Docker layer)
# Subsequent rebuilds are fast due to layer cache
docker compose up -d --build
```

### Step 4: Watch embedding service start
```bash
docker compose logs -f embedding
# Wait for:
# embedding_model_ready model=BAAI/bge-m3
```

---

## 9. Testing Checklist

Run these in order after full stack is up.

### 9.1 Embedding service health
```bash
curl http://localhost:8080/health
# Expected: { "status": "ok", "model_loaded": true }
```

### 9.2 Embed test
```bash
curl -s -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["Hôm nay tôi stress vì công việc"], "mode": "passage"}' \
  | python -c "import json,sys; d=json.load(sys.stdin); print(len(d['embeddings'][0]), 'dims')"
# Expected: 1024 dims
```

### 9.3 Register and login
```bash
# Register
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test1234!"}' | python -m json.tool

# Login → get JWT
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test1234!"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

echo "TOKEN=$TOKEN"
```

### 9.4 Create a transaction (triggers ingestion)
```bash
curl -s -X POST http://localhost:8000/transactions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 750000,
    "currency": "VND",
    "type": "expense",
    "category": "shopping",
    "note": "Mua mô hình Gundam sau buổi phỏng vấn căng thẳng",
    "transaction_date": "2026-04-09"
  }' | python -m json.tool
```

### 9.5 Write a journal entry (triggers ingestion)
```bash
curl -s -X POST http://localhost:8000/journal/entries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Hôm nay mình stress vì phỏng vấn và deadline dự án. Cảm thấy quá tải. Cuối cùng lại lên Shopee mua figure để giải stress. Biết là không tốt nhưng vẫn làm."
  }' | python -m json.tool
```

### 9.6 Verify chunks were stored (check DB directly)
```bash
docker compose exec postgres psql -U fw -d insight_db -c \
  "SELECT source_type, chunk_index, left(content, 80) as preview, (embedding IS NOT NULL) as has_embedding FROM document_chunks;"
```

### 9.7 RAG chat — test retrieval + generation
```bash
curl -s -X POST http://localhost:8000/insights/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tại sao tôi hay mua đồ khi stress?", "stream": false}'
```

Expected response includes:
- Specific reference to the shopping transaction and journal entry you just created
- Response in Vietnamese (matches question language)
- `sources` array listing which `document_chunks` were used

### 9.8 Test SSE streaming
```bash
curl -N -X POST http://localhost:8000/insights/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tóm tắt tình hình tài chính và tâm trạng của tôi", "stream": true}'
# Each line: data: {"delta": "..."}
# Last line: data: {"done": true, "sources": [...]}
```

---

## 10. Mapping to Aviation Use Case

The same pipeline works for aviation/enterprise with minimal changes:

| Financial Wellness | Aviation PoC |
|---|---|
| `journal_entries.content` | Flight incident reports, maintenance logs |
| `transactions.note` + metadata | Passenger complaints + `{flight_id, route, class}` |
| `mood_entries.note` + score | Customer satisfaction surveys + score |
| `user_id` filter | `airline_id` or `customer_segment_id` filter |
| Category/date filters in JSONB | Route, aircraft type, flight date filters |
| "Why do I overspend when stressed?" | "What are the top complaint themes on HAN-SGN route?" |
| `BAAI/bge-m3` (multilingual) | Same model — handles English aviation jargon |
| `POST /insights/chat` (SSE) | `POST /reports/query` — same pattern |

**Key message when presenting:**  
> "The embedding-service, vector store, and RAG pipeline are domain-agnostic. I swap the document format functions and the system prompt, and the aviation version works."

---

## 11. What Is NOT in Phase 2 (Deferred)

| Feature | Why deferred | Phase |
|---|---|---|
| Reranker (cross-encoder) | Adds ~500ms latency, overkill for small user corpus | 3 |
| Semantic chunking (LLM-based) | Extra LLM call on ingest, recursive chunking is sufficient | 3 |
| Conversation history | Needs additional table + context injection | 3 |
| PII masking (Presidio) | More relevant for enterprise/aviation production | 3 |
| Embedding cache (Redis) | `ON CONFLICT DO UPDATE` already prevents re-embedding same source | 3 |
| Ragas evaluation | Needs curated test set — can run as offline script | 3 |

---

## 12. Troubleshooting

**`embedding_model_ready` never appears in logs**  
→ BGE-M3 is still downloading or OOM. Check: `docker compose logs embedding`  
→ Ensure Docker Desktop has at least 6 GB RAM allocated

**`POST /insights/chat` returns `"Embedding service is temporarily unavailable."`**  
→ embedding-service is not healthy yet. Wait for `model_loaded: true` on `/health`.

**Chunks exist in DB but `embedding IS NOT NULL` is false**  
→ Ingestion task ran but embedding call failed. Check: `docker compose logs insight | grep ingest`

**Gemini returns 429 (rate limit)**  
→ Free tier is 15 RPM. The Kong rate limit at 10/min should prevent this. If testing rapidly, add a sleep between requests.

**`vector` type not found in migration**  
→ The postgres image must be `pgvector/pgvector:pg16`, not `postgres:16-alpine`. Check `docker-compose.yaml`.
