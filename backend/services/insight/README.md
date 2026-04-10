# Insight Service — Phase 2: RAG Pipeline

This document covers everything needed to **run, test, and understand** the Phase 2 RAG implementation.

---

## Prerequisites

Before running Phase 2, make sure you have:

1. **Docker Desktop** running with at least **8 GB RAM** allocated
2. **Gemini API key** — free at [aistudio.google.com](https://aistudio.google.com) → Get API key
3. **`.env` file** in `backend/` with the key set:

```env
GEMINI_API_KEY=AIzaSy...your_key_here
```

---

## Quick Start

```bash
cd backend

# First build takes 10–20 minutes (downloads BGE-M3 ~2.2 GB + torch ~500 MB)
# Subsequent builds are fast — Docker caches the model layer
docker compose up -d --build
```

Wait for the embedding service to finish loading the model:

```bash
docker compose logs -f embedding
# Ready when you see:
# embedding_model_ready model=BAAI/bge-m3
```

---

## Architecture

```
User POST /insights/chat
        │
        ▼
      Kong  ←── JWT verify + rate limit (10 req/min)
        │
        ▼
insight-service
  ├── 1. embed question → POST http://embedding:8080/embed
  ├── 2. cosine search  → document_chunks WHERE user_id = ?
  ├── 3. build context  → dedup + format + truncate to 6000 tokens
  ├── 4. call Gemini    → gemini-2.0-flash streaming
  └── 5. SSE stream     → data: {"delta": "..."} chunks
                          data: {"done": true, "sources": [...]}

RabbitMQ events (from transaction + journal services)
        │
        ▼
insight-service consumer
  ├── Phase 1: upsert insight (rule-based text) ← unchanged
  └── Phase 2: asyncio.create_task(ingest_document)
        ├── format document text
        ├── chunk (recursive, 512 tokens, 64 overlap)
        ├── POST http://embedding:8080/embed
        └── INSERT INTO document_chunks ON CONFLICT DO UPDATE
```

---

## Services Added / Changed

| Service | Change |
|---|---|
| `embedding` | **New** — BGE-M3 model server on port 8080 |
| `insight` | Added RAG package, chat router, new env vars |
| `insight-migrator` | Runs new migration `0002_document_chunks` |
| `kong` | Added `POST /insights/chat` route |

---

## Testing Step by Step

Run these commands in order. All go through Kong at `http://localhost:8000`.

### Step 1 — Confirm embedding service is healthy

```bash
curl http://localhost:8080/health
```

Expected:
```json
{ "status": "ok", "model_loaded": true }
```

### Step 2 — Smoke test the embed endpoint

```bash
curl -s -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["test"], "mode": "passage"}'
```

Expected: `{"embeddings": [[...1024 floats...]], "model": "BAAI/bge-m3", "dimension": 1024}`

### Step 3 — Register a user

```bash
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test1234!"}' | python -m json.tool
```

### Step 4 — Login and capture the token

**PowerShell:**
```powershell
$response = Invoke-RestMethod -Method POST -Uri "http://localhost:8000/auth/login" `
  -ContentType "application/json" `
  -Body '{"email": "test@example.com", "password": "Test1234!"}'
$TOKEN = $response.access_token
Write-Host "TOKEN=$TOKEN"
```

**Bash:**
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "Test1234!"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
echo $TOKEN
```

### Step 5 — Create a transaction (triggers ingestion)

**PowerShell:**
```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/transactions" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -ContentType "application/json" `
  -Body '{
    "amount": 750000,
    "currency": "VND",
    "type": "expense",
    "category": "shopping",
    "note": "Mua mô hình Gundam sau buổi phỏng vấn căng thẳng",
    "transaction_date": "2026-04-09"
  }'
```

**Bash:**
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

Wait ~5 seconds for ingestion to complete in the background.

### Step 6 — Write a journal entry (triggers ingestion)

**PowerShell:**
```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/journal/entries" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -ContentType "application/json" `
  -Body '{
    "content": "Hôm nay mình stress vì phỏng vấn và deadline dự án. Cảm thấy quá tải. Cuối cùng lại lên Shopee mua figure để giải stress. Biết là không tốt nhưng vẫn làm vì cần cảm giác kiểm soát thứ gì đó."
  }'
```

**Bash:**
```bash
curl -s -X POST http://localhost:8000/journal/entries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hôm nay mình stress vì phỏng vấn và deadline dự án. Cảm thấy quá tải. Cuối cùng lại lên Shopee mua figure để giải stress. Biết là không tốt nhưng vẫn làm vì cần cảm giác kiểm soát thứ gì đó."}' \
  | python -m json.tool
```

### Step 7 — Verify chunks are stored in DB

```bash
docker compose exec postgres psql -U fw -d insight_db -c \
  "SELECT source_type, chunk_index, left(content, 80) AS preview, (embedding IS NOT NULL) AS embedded FROM document_chunks;"
```

Expected output:
```
  source_type   | chunk_index |                  preview                               | embedded
----------------+-------------+---------------------------------------------------------+---------
 transaction    |           0 | 2026-04-09: expense 750,000 VND [shopping]              | t
 journal_entry  |           0 | [Journal 2026-04-09]                                    | t
```

### Step 8 — RAG chat (non-streaming)

**PowerShell:**
```powershell
Invoke-RestMethod -Method POST -Uri "http://localhost:8000/insights/chat" `
  -Headers @{ Authorization = "Bearer $TOKEN" } `
  -ContentType "application/json" `
  -Body '{"question": "Tại sao tôi hay mua đồ khi stress?", "stream": false}'
```

**Bash:**
```bash
curl -s -X POST http://localhost:8000/insights/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tại sao tôi hay mua đồ khi stress?", "stream": false}'
```

The response should reference your actual transaction and journal entry — not generic advice.

### Step 9 — RAG chat (SSE streaming)

**PowerShell:**
```powershell
# PowerShell doesn't handle SSE natively, use curl.exe
curl.exe -N -X POST http://localhost:8000/insights/chat `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"question": "Tóm tắt tình hình tài chính và tâm trạng của tôi", "stream": true}'
```

**Bash:**
```bash
curl -N -X POST http://localhost:8000/insights/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tóm tắt tình hình tài chính và tâm trạng của tôi", "stream": true}'
```

Expected SSE format:
```
data: {"delta": "Dựa trên "}
data: {"delta": "lịch sử của bạn..."}
...
data: {"done": true, "sources": [{"source_type": "transaction", "similarity": 0.87}, ...]}
```

---

## What Gets Ingested and When

| Action | What happens |
|---|---|
| User creates a transaction | insight-service consumer receives event → chunks formatted with `date + amount + category + note` → embedded → stored |
| User writes a journal entry | consumer receives event → recursive chunking (512 tokens, 64 overlap) → embedded → stored |
| User logs a mood entry | consumer receives event → single chunk formatted with `score + note` → embedded → stored |

Ingestion is **fire-and-forget** — consumer ACKs the RabbitMQ message immediately regardless of embedding speed. Failures are logged but do not affect Phase 1 insights.

---

## Document Format (why it matters)

The text embedded determines what the vector search can find:

```
# Transaction — date + amount + category embedded as text
"2026-04-09: expense 750,000 VND [shopping]
Mua mô hình Gundam sau buổi phỏng vấn căng thẳng"

# Journal chunk — date prefix on every chunk
"[Journal 2026-04-09]
Hôm nay mình stress vì phỏng vấn và deadline..."

# Mood — score as text so it's searchable
"[Mood 2026-04-09] Score: 2/5
Cảm thấy mệt mỏi và áp lực"
```

If only the note were embedded (without date/amount/category), a query like "tháng 4 tôi tiêu gì" would not match because the vector would contain no date information.

---

## Troubleshooting

**`model_loaded: false` from `/health`**
→ BGE-M3 is still loading. Wait and retry in 60 seconds.

**`Embedding service is temporarily unavailable`**
→ embedding container not healthy yet. Check: `docker compose logs embedding`

**Chunks in DB but `embedded = f`**
→ Ingestion task ran but embedding call failed. Check: `docker compose logs insight | grep ingest`

**Gemini returns 429 rate limit**
→ Free tier is 15 RPM. Kong limits to 10/min. Wait 1 minute and retry.

**`vector type not found` in migration**
→ postgres image must be `pgvector/pgvector:pg16`. Check `docker-compose.yaml`.

**Chat returns "I do not have enough context"**
→ Create at least one transaction or journal entry first (Step 5/6), wait 5 seconds for ingestion, then retry.

---

## New Files Reference

```
backend/
  services/
    embedding/                        ← NEW microservice
      Dockerfile
      pyproject.toml
      src/embedding/
        __init__.py
        config.py
        model.py                      ← BGE-M3 singleton loader
        main.py                       ← FastAPI app + /health
        routers/
          embed.py                    ← POST /embed endpoint

    insight/
      migrations/versions/
        0002_document_chunks.py       ← NEW: vector table + HNSW index
      src/insight/
        models/
          chunk.py                    ← NEW: DocumentChunk SQLAlchemy model
        rag/                          ← NEW package
          chunker.py                  ← recursive text chunking
          ingestion.py                ← format + embed + upsert pipeline
          retrieval.py                ← pgvector cosine search
          context_builder.py         ← dedup, format, truncate
          llm_client.py              ← Gemini Flash 2.5 streaming
          prompt.py                  ← system prompt template
        routers/
          chat.py                    ← NEW: POST /insights/chat (SSE)
```
