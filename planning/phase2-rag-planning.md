# Phase 2 — RAG Pipeline Planning

> **Mục đích document này:** Spec đủ chi tiết để implement không cần đoán.  
> **Không code ở đây** — chỉ thiết kế decisions, schema, interfaces, và luồng.  
> **Stack đã confirm:** BGE-M3 (local embedding), Gemini Flash 2.5 (LLM), pgvector (vector store), SSE (streaming).

---

## Context — Phase 1 đã có gì

Đọc kỹ trước khi implement để không làm lại:

```
backend/
  services/
    identity/       ← auth, JWT RS256, JWKS endpoint
    transaction/    ← CRUD + publish → RabbitMQ fanout "transactions.events"
    journal/        ← entries + moods + publish → RabbitMQ fanout "journal.events"
    insight/        ← consume events → upsert insight table (STUB, phase 2 replaces)
    notification/   ← consume events → rule-based alerts
  docker-compose.yml
  kong/kong.yml
```

**insight-service phase 1 stubs (cần replace):**
- `services/insight_service.py` → `refresh_spending_insight()` và `refresh_mood_insight()` đang return hardcoded text
- `models/insight.py` → `Insight` table đã có, migration đã chạy `CREATE EXTENSION IF NOT EXISTS vector`
- `messaging/consumers.py` → `TransactionInsightConsumer.process()` và `JournalInsightConsumer.process()` gọi stubs trên

**Postgres image hiện tại là `postgres:16-alpine`** — **không có pgvector**.  
Phase 2 cần đổi sang `pgvector/pgvector:pg16` trong `docker-compose.yml`.

---

## Thay đổi docker-compose.yml

```yaml
# Dòng cũ:
postgres:
  image: postgres:16-alpine

# Thay bằng:
postgres:
  image: pgvector/pgvector:pg16
```

Thêm `embedding-service` vào compose (xem spec bên dưới).  
Thêm env vars cho `insight-service`:

```yaml
insight:
  environment:
    # ... giữ nguyên env cũ, thêm:
    EMBEDDING_SERVICE_URL: http://embedding:8080
    GEMINI_API_KEY: ${GEMINI_API_KEY:-}
    GEMINI_MODEL: gemini-2.0-flash
    RAG_TOP_K: 8
    RAG_CHUNK_SIZE: 512
    RAG_CHUNK_OVERLAP: 64
```

---

## Service mới: embedding-service

### Vị trí
```
backend/services/embedding/
  src/embedding/
    main.py
    config.py
    model.py       ← BGE-M3 singleton loader
    routers/
      embed.py
  pyproject.toml
  Dockerfile
```

### Mục đích
Tách embedding model ra service riêng vì:
1. BGE-M3 ~2.2GB — không muốn load trong mọi container
2. Có thể scale độc lập
3. Swap model (BGE-M3 → khác) không ảnh hưởng pipeline

### API contract

**POST /embed**
```json
// Request
{
  "texts": ["string", "string"],
  "mode": "query" | "passage"   // thêm prefix tương ứng cho BGE
}

// Response
{
  "embeddings": [[0.1, 0.2, ...], [...]],  // list of float[1024]
  "model": "BAAI/bge-m3",
  "dimension": 1024
}
```

**GET /health**
```json
{ "status": "ok", "model_loaded": true }
```

### Model loading
- Load `BAAI/bge-m3` khi startup, store trong `app.state.model`
- `sentence_transformers.SentenceTransformer("BAAI/bge-m3")`
- `normalize_embeddings=True` — quan trọng cho cosine similarity
- Prefix: `query: <text>` cho query, `passage: <text>` cho documents

### pyproject.toml deps
```
sentence-transformers>=3.0.0
torch>=2.2.0          # CPU only, không cần CUDA
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
structlog>=24.2.0
```

### Dockerfile
```dockerfile
FROM python:3.12-slim AS base
RUN pip install uv
WORKDIR /app
COPY pyproject.toml .
RUN uv venv && uv pip install --no-cache -e .

# Pre-download model vào image — không download lúc runtime
RUN /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

COPY src/ src/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

FROM base AS runtime
EXPOSE 8080
CMD ["uvicorn", "embedding.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Lưu ý:** Build lần đầu sẽ lâu (download ~2.2GB model). Sau đó được cache trong Docker layer.

### docker-compose entry
```yaml
embedding:
  build: ./services/embedding
  ports:
    - "8080:8080"
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 60s   # model load cần thời gian
```

---

## Schema mới trong insight_db

### Migration 0002 — document_chunks table

```sql
-- insight_db, migration 0002_document_chunks

CREATE TABLE document_chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL,

    -- Source tracking
    source_type TEXT NOT NULL,     -- 'journal_entry' | 'mood_entry' | 'transaction'
    source_id   UUID NOT NULL,     -- FK tới record gốc trong service tương ứng
                                   -- Không dùng FK thật vì cross-DB

    -- Chunk content
    chunk_index INT  NOT NULL,     -- thứ tự chunk trong document gốc (0-based)
    content     TEXT NOT NULL,     -- text đã được format (xem Document Format bên dưới)
    
    -- Vector
    embedding   vector(1024),      -- BGE-M3 output dimension

    -- Metadata — dùng để filter TRƯỚC vector search (hybrid retrieval)
    metadata    JSONB NOT NULL DEFAULT '{}',
    -- metadata schema theo source_type:
    -- transaction: { "category": "shopping", "amount": "750000", "currency": "VND",
    --                "transaction_date": "2026-04-08", "type": "expense" }
    -- journal:     { "word_count": 120, "created_at": "2026-04-08T..." }
    -- mood:        { "score": 2, "created_at": "2026-04-08T..." }

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index cho vector similarity search (cosine) — HNSW tốt hơn IVFFlat cho insert liên tục
CREATE INDEX ix_chunks_embedding ON document_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Index cho multi-tenant filter (luôn filter user_id trước khi vector search)
CREATE INDEX ix_chunks_user_source ON document_chunks (user_id, source_type);

-- Unique: mỗi (source_id, chunk_index) là duy nhất → upsert idempotent
CREATE UNIQUE INDEX uq_chunks_source_chunk ON document_chunks (source_id, chunk_index);
```

**Tại sao HNSW thay IVFFlat:**  
IVFFlat cần training (phải có đủ data trước khi build index). HNSW insert real-time tốt hơn, phù hợp khi document được thêm liên tục theo event.

---

## Document Format — cách convert raw data thành chunk text

Đây là quyết định quan trọng nhất, quyết định chất lượng retrieval.

### Transaction → document text
```
# Template:
"{transaction_date}: {type} {amount} {currency} [{category}]
{note}"

# Ví dụ:
"2026-04-08: expense 750,000 VND [shopping]
Mua mô hình sau buổi phỏng vấn căng thẳng"

# Nếu note rỗng:
"2026-04-08: expense 750,000 VND [shopping]"
```
1 transaction = 1 chunk (không split). Metadata lưu vào `metadata` JSONB.

### Journal entry → chunks
```
# Chunking strategy: recursive/structural
# 1. Split theo "\n\n" (paragraph boundary)
# 2. Nếu paragraph > RAG_CHUNK_SIZE tokens: split theo ". " (sentence)
# 3. Overlap: RAG_CHUNK_OVERLAP tokens giữa các chunks liền kề

# Template mỗi chunk:
"[Journal {created_at_date}]
{chunk_content}"

# Ví dụ chunk 0:
"[Journal 2026-04-08]
Hôm nay mình stress vì deadline dự án..."

# Ví dụ chunk 1 (có overlap với chunk 0):
"[Journal 2026-04-08]
...deadline dự án. Cuối cùng lại lên Shopee mua 2 cái figure để giải stress."
```

### Mood entry → document text
```
# Template:
"[Mood {created_at_date}] Score: {score}/5
{note}"

# Ví dụ:
"[Mood 2026-04-08] Score: 2/5
Cảm thấy mệt mỏi và áp lực sau cuộc họp"

# Nếu note rỗng:
"[Mood 2026-04-08] Score: 2/5"
```
1 mood entry = 1 chunk.

---

## Ingestion Pipeline — trong insight-service

### Trigger
Khi consumer nhận event (transaction hoặc journal), sau khi upsert insight (phase 1 behavior), **thêm bước embed và store chunks**.

### Flow

```
event received
    │
    ├─ [phase 1] upsert insight (giữ nguyên)
    │
    └─ [phase 2 thêm] ingest_document(source_type, source_id, user_id, content, metadata)
            │
            ├─ format_document(content, metadata) → document_text
            ├─ chunk(document_text) → List[str]  (recursive chunking)
            ├─ POST http://embedding:8080/embed   → embeddings: List[List[float]]
            ├─ for each (chunk, embedding):
            │     INSERT INTO document_chunks ... ON CONFLICT (source_id, chunk_index) DO UPDATE
            └─ done (fire and forget nếu embed service chậm — không block consumer ACK)
```

**Quan trọng:** Ingestion không được block consumer ACK. Nếu embedding service chậm hoặc down, consumer vẫn ACK message sau khi upsert insight phase 1. Ingestion failure → log error, chunk không được embed, user vẫn nhận insight phase 1 (rule-based).

Implement pattern: `asyncio.create_task(ingest_document(...))` — fire and forget với error handling riêng.

### Chunking implementation

```python
# services/insight/src/insight/rag/chunker.py

def chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """
    Recursive/structural chunking:
    1. Split by "\n\n" (paragraph)
    2. If paragraph > chunk_size tokens: split by ". " (sentence)
    3. Apply overlap between consecutive chunks
    
    Token counting: approximate với len(text.split()) * 1.3
    (không dùng tokenizer thật — overhead không xứng)
    """
    ...
```

---

## RAG Query Pipeline — trong insight-service

### Endpoint mới

**POST /insights/chat**
```json
// Request
{
  "question": "Tại sao dạo này tôi tiêu nhiều hơn?",
  "stream": true
}

// Response (SSE stream, Content-Type: text/event-stream)
data: {"delta": "Dựa trên "}
data: {"delta": "lịch sử của bạn, "}
data: {"delta": "tôi nhận thấy..."}
data: {"done": true, "sources": [...]}
```

### RAG flow chi tiết

```
user_question (str)
    │
    1. EMBED QUERY
    │   POST embedding-service /embed { texts: [question], mode: "query" }
    │   → query_vector: List[float]  (1024 dims)
    │
    2. HYBRID RETRIEVAL (trong insight-service, query insight_db trực tiếp)
    │   
    │   SELECT c.content, c.source_type, c.metadata, c.created_at,
    │          1 - (c.embedding <=> $query_vector) AS similarity
    │   FROM document_chunks c
    │   WHERE c.user_id = $user_id           ← multi-tenant isolation, BẮT BUỘC
    │     AND c.embedding IS NOT NULL        ← skip chưa được embed
    │   ORDER BY c.embedding <=> $query_vector   ← cosine distance ascending
    │   LIMIT $RAG_TOP_K                     ← default 8
    │
    │   Kết quả: List[RetrievedChunk]
    │
    3. CONTEXT BUILD
    │   - Dedup: bỏ chunks trùng source_id + nội dung tương tự (similarity > 0.97)
    │   - Format: mỗi chunk thành "Source [{source_type} {date}]: {content}"
    │   - Assemble: join theo thứ tự similarity desc
    │   - Truncate: nếu tổng > 6000 tokens, bỏ chunk cuối
    │
    4. PROMPT BUILD
    │   System prompt (xem bên dưới)
    │   + Context block
    │   + User question
    │
    5. LLM CALL (Gemini Flash 2.5, streaming)
    │   - model: "gemini-2.0-flash"
    │   - stream: True
    │   → async generator of text deltas
    │
    6. SSE STREAM
        - yield each delta as "data: {json}\n\n"
        - on completion: yield sources list
```

### System prompt template

```
You are a personal financial wellness coach with access to the user's
spending history and journal entries. You provide empathetic, specific
insights based only on the provided context — never fabricate data.

If the context does not contain enough information to answer the question,
say so honestly and suggest the user log more entries.

Always respond in the same language as the user's question.
Keep responses concise (under 200 words) unless the user asks for detail.

Today's date: {today}

--- User's personal context ---
{context}
--- End of context ---
```

---

## File structure — phase 2 additions

```
services/
  embedding/                     ← NEW service
    src/embedding/
      main.py
      config.py
      model.py                   ← BGE-M3 singleton
      routers/
        embed.py
    pyproject.toml
    Dockerfile

  insight/
    src/insight/
      rag/                       ← NEW package
        __init__.py
        chunker.py               ← recursive text chunking
        ingestion.py             ← format + chunk + call embedding-service + upsert
        retrieval.py             ← hybrid pgvector query
        context_builder.py       ← dedup, format, truncate
        llm_client.py            ← Gemini API call, streaming
        prompt.py                ← system prompt template
      models/
        insight.py               ← giữ nguyên
        chunk.py                 ← NEW: DocumentChunk SQLAlchemy model
      routers/
        insight.py               ← giữ nguyên GET /insights
        chat.py                  ← NEW: POST /insights/chat (SSE)
      services/
        insight_service.py       ← phase 1 stubs → replace với LLM call
      messaging/
        consumers.py             ← thêm asyncio.create_task(ingest) sau upsert
    migrations/
      versions/
        0001_initial.py          ← giữ nguyên
        0002_document_chunks.py  ← NEW migration
```

---

## SQLAlchemy model — DocumentChunk

```python
# services/insight/src/insight/models/chunk.py

class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_index", name="uq_chunks_source_chunk"),
        Index("ix_chunks_user_source", "user_id", "source_type"),
        # HNSW index tạo trong migration, không thể tạo trong __table_args__
    )
```

**Import vector type:** `from pgvector.sqlalchemy import Vector`

---

## insight-service config additions

```python
# Thêm vào class Settings trong config.py
embedding_service_url: str = "http://embedding:8080"
gemini_api_key: str = ""
gemini_model: str = "gemini-2.0-flash"
rag_top_k: int = 8
rag_chunk_size: int = 512
rag_chunk_overlap: int = 64
```

---

## Gemini client — streaming interface

Dùng `google-generativeai` SDK:

```python
# pip install google-generativeai>=0.8.0 (thêm vào insight pyproject.toml)

import google.generativeai as genai
from collections.abc import AsyncGenerator

async def stream_llm(prompt: str, context: str, question: str) -> AsyncGenerator[str, None]:
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    
    full_prompt = build_prompt(context, question)  # từ prompt.py
    
    response = await model.generate_content_async(
        full_prompt,
        stream=True,
        generation_config={"max_output_tokens": 512, "temperature": 0.7},
    )
    
    async for chunk in response:
        if chunk.text:
            yield chunk.text
```

---

## SSE endpoint — router/chat.py

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import json

router = APIRouter(prefix="/insights", tags=["insights"])

@router.post("/chat")
async def chat(
    payload: ChatRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    async def event_stream():
        # 1. embed query
        # 2. retrieve chunks
        # 3. build context
        # 4. stream LLM
        async for delta in stream_llm(...):
            yield f"data: {json.dumps({'delta': delta})}\n\n"
        
        # 5. send sources
        yield f"data: {json.dumps({'done': True, 'sources': [...]})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## Kong — thêm route mới

```yaml
# Thêm vào kong/kong.yml trong service insight-service
routes:
  - name: insights-list
    paths: [/insights]
    methods: [GET]
  - name: insights-chat          # NEW
    paths: [/insights/chat]
    methods: [POST]
    plugins:
      - name: rate-limiting
        config:
          minute: 10             # LLM call tốn tiền — giới hạn chặt
          policy: local
```

---

## Dependencies giữa services khi startup

```
postgres (pgvector/pgvector:pg16)
    └─▶ insight-migrator (runs 0002_document_chunks)
            └─▶ insight-service

embedding-service (độc lập, không cần DB)
    └─▶ insight-service (cần embedding-service healthy trước khi nhận query)
        (nhưng không cần trước khi startup — chỉ cần khi process request)
```

`embedding-service` không cần `depends_on` trong compose — insight-service sẽ retry HTTP call nếu embedding chưa sẵn sàng.

---

## Những thứ KHÔNG implement trong Phase 2

Để tránh scope creep:

| Feature | Lý do bỏ |
|---|---|
| Reranker (cross-encoder) | Overkill cho data volume nhỏ, thêm latency |
| Ragas evaluation | Setup riêng trong script test, không integrate vào service |
| PII masking (Presidio) | Phase 3, relevant hơn cho aviation |
| Semantic chunking (LLM-based split) | Phase 3 |
| Embedding cache (Redis) | BGE-M3 đã nhanh, upsert ON CONFLICT handle dedup |
| Conversation history | Phase 3, cần thêm table |
| Refresh token / revocation | Phase 3, đã note trong phase 1 README |

---

## Test checklist sau khi implement

Sau khi stack chạy, verify theo thứ tự:

```bash
# 1. Embedding service healthy và load model xong
curl http://localhost:8080/health
# → { "status": "ok", "model_loaded": true }

# 2. Embed test
curl -X POST http://localhost:8080/embed \
  -H "Content-Type: application/json" \
  -d '{"texts": ["test sentence"], "mode": "passage"}'
# → { "embeddings": [[...1024 floats...]], "dimension": 1024 }

# 3. Tạo transaction → trigger ingestion
# (sau khi register + login, lấy TOKEN)
curl -X POST http://localhost:8000/transactions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": 750000, "currency": "VND", "type": "expense",
       "category": "shopping",
       "note": "Mua mô hình sau buổi phỏng vấn căng thẳng",
       "transaction_date": "2026-04-08"}'

# 4. Viết journal
curl -X POST http://localhost:8000/journal/entries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Hôm nay stress vì phỏng vấn. Cuối cùng lại lên Shopee mua figure. Cảm thấy tạm thời thư giãn nhưng tội lỗi."}'

# 5. Verify chunks được lưu (query trực tiếp postgres)
# psql -h localhost -U fw -d insight_db
# SELECT source_type, chunk_index, content, (embedding IS NOT NULL) as has_embedding
# FROM document_chunks WHERE user_id = '<your-user-id>';

# 6. RAG chat
curl -X POST http://localhost:8000/insights/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Tại sao tôi hay mua đồ khi stress?", "stream": false}'
# → response dựa trên context thực từ transaction + journal
```

---

## Mapping sang Aviation (cho slide trình bày)

Kỹ thuật giống hệt, domain data khác:

| Financial Wellness | Aviation use case |
|---|---|
| `journal_entries.content` | Flight incident reports, complaint letters |
| `transactions.note` + metadata | Ticket complaints + `{flight_id, route, class}` |
| `mood_entries.note` | Customer satisfaction comments + score |
| Multi-tenant filter `user_id` | Filter `airline_id` hoặc `customer_segment` |
| Hybrid: vector + SQL filter by date | Hybrid: vector + filter by `route`, `aircraft_type` |
| BGE-M3 multilingual | Handles English aviation jargon |
| POST /insights/chat (SSE) | Document search chatbot, complaint Q&A |
| HNSW index realtime insert | Realtime ingestion khi complaint mới submit |

**Key message khi present:** "Pipeline này không phụ thuộc vào domain. Tôi swap data source và system prompt là có aviation RAG."