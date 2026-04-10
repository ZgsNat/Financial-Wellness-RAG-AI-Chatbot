"""
Ingestion pipeline — formats, chunks, embeds, and upserts document chunks.

Called fire-and-forget from consumers via asyncio.create_task().
Failures are logged but do NOT propagate — consumer ACK is never blocked.

Document format per planning doc (determines retrieval quality):
  - transaction  → "{date}: {type} {amount} {currency} [{category}]\\n{note}"
  - journal      → chunked with prefix "[Journal {date}]\\n{chunk_content}"
  - mood         → "[Mood {date}] Score: {score}/5\\n{note}"
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from insight.config import get_settings
from insight.rag.chunker import chunk_text
from insight.rag.preprocessor import preprocess_document

logger = structlog.get_logger()
settings = get_settings()


# ── Document formatters ───────────────────────────────────────────────────────

def _format_transaction(payload: dict[str, Any]) -> tuple[str, dict]:
    """Format a transaction event payload into (document_text, metadata).

    Phase 2.5 enrichment: generates natural Vietnamese text so the chunk
    competes semantically with journal entries for finance-related queries.

    Old format (avg ~41 chars, structured/English):
        "2026-03-01: expense 450,000 VND [food]\\nBún bò buổi sáng"

    New format (avg ~140 chars, natural Vietnamese):
        "Chi tiêu thực phẩm & ăn uống ngày 2026-03-01: 450,000 VND.
         Ghi chú: Bún bò buổi sáng.
         Giao dịch: chi tiêu. Danh mục: thực phẩm & ăn uống."
    """
    # ── Category label map (Vietnamese) ──────────────────────────────────────
    _CAT_LABELS: dict[str, str] = {
        "food":          "thực phẩm & ăn uống",
        "shopping":      "mua sắm",
        "transport":     "di chuyển & phương tiện",
        "health":        "sức khỏe & y tế",
        "entertainment": "giải trí",
        "education":     "học tập & giáo dục",
        "utilities":     "hóa đơn tiện ích",
        "other":         "chi tiêu khác",
    }
    _TYPE_LABELS: dict[str, str] = {
        "expense": "Chi tiêu",
        "income":  "Thu nhập",
    }

    date = payload.get("transaction_date") or payload.get("created_at", "")[:10]
    tx_type  = payload.get("type", "expense")
    amount   = payload.get("amount", 0)
    currency = payload.get("currency", "VND")
    category = payload.get("category", "")
    note     = preprocess_document(payload.get("note", ""))

    # Format amount with thousands separator
    try:
        amount_fmt = f"{int(float(amount)):,}"
    except (ValueError, TypeError):
        amount_fmt = str(amount)

    cat_label  = _CAT_LABELS.get(category, category)
    type_label = _TYPE_LABELS.get(tx_type, tx_type.capitalize())

    # Headline: natural Vietnamese — matches user query patterns directly
    doc = f"{type_label} {cat_label} ngày {date}: {amount_fmt} {currency}."
    if note:
        doc += f"\nGhi chú: {note}."
    # Taxonomy line: repeat label (boosts similarity for category-targeted queries)
    doc += f"\nGiao dịch: {type_label.lower()}. Danh mục: {cat_label}."

    metadata = {
        "category": category,
        "amount": str(amount),
        "currency": currency,
        "transaction_date": date,
        "type": tx_type,
    }
    return doc, metadata


def _format_journal(payload: dict[str, Any], chunk_content: str) -> tuple[str, dict]:
    """Format one journal chunk with its header prefix."""
    created_at = payload.get("created_at", "")
    date = created_at[:10] if created_at else datetime.now(timezone.utc).date().isoformat()
    word_count = len(payload.get("content", "").split())

    chunk_content = preprocess_document(chunk_content)
    doc = f"[Journal {date}]\n{chunk_content}"
    metadata = {
        "word_count": word_count,
        "created_at": created_at,
    }
    return doc, metadata


def _format_mood(payload: dict[str, Any]) -> tuple[str, dict]:
    """Format a mood entry payload into (document_text, metadata)."""
    created_at = payload.get("created_at", "")
    date = created_at[:10] if created_at else datetime.now(timezone.utc).date().isoformat()
    score = payload.get("score", "")
    note = preprocess_document(payload.get("note", ""))

    doc = f"[Mood {date}] Score: {score}/5"
    if note:
        doc += f"\n{note}"

    metadata = {
        "score": str(score),
        "created_at": created_at,
    }
    return doc, metadata


# ── Embedding client ──────────────────────────────────────────────────────────

async def _embed_texts(texts: list[str], mode: str = "passage") -> list[list[float]]:
    """POST to embedding-service and return list of float[1024] vectors."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.embedding_service_url}/embed",
            json={"texts": texts, "mode": mode},
        )
        response.raise_for_status()
        return response.json()["embeddings"]


# ── Upsert ────────────────────────────────────────────────────────────────────

async def _upsert_chunks(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_type: str,
    source_id: uuid.UUID,
    chunks: list[tuple[str, dict]],  # (content, metadata)
    embeddings: list[list[float]],
) -> None:
    """Upsert (source_id, chunk_index) pairs — idempotent."""
    for i, ((content, metadata), embedding) in enumerate(zip(chunks, embeddings)):
        vector_literal = f"[{','.join(str(v) for v in embedding)}]"
        await db.execute(
            text(
                """
                INSERT INTO document_chunks
                    (id, user_id, source_type, source_id, chunk_index,
                     content, embedding, metadata, created_at, updated_at)
                VALUES
                    (gen_random_uuid(), :user_id, :source_type, :source_id, :chunk_index,
                     :content, :embedding ::vector, :metadata ::jsonb, now(), now())
                ON CONFLICT (source_id, chunk_index)
                DO UPDATE SET
                    content    = EXCLUDED.content,
                    embedding  = EXCLUDED.embedding,
                    metadata   = EXCLUDED.metadata,
                    updated_at = now()
                """
            ),
            {
                "user_id": str(user_id),
                "source_type": source_type,
                "source_id": str(source_id),
                "chunk_index": i,
                "content": content,
                "embedding": vector_literal,
                "metadata": json.dumps(metadata),
            },
        )
    await db.commit()


# ── Public entry point ────────────────────────────────────────────────────────

async def ingest_document(
    db_session_factory: async_sessionmaker,
    source_type: str,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: dict[str, Any],
) -> None:
    """
    Format, chunk, embed, and upsert one document.

    *source_type* must be one of: 'transaction', 'journal_entry', 'mood_entry'.
    *payload*     is the raw event body from the message broker.

    This function runs inside asyncio.create_task() — errors are caught and
    logged; they never propagate to the caller.
    """
    try:
        logger.info("ingest_start", source_type=source_type, source_id=str(source_id))

        if source_type == "transaction":
            doc_text, metadata = _format_transaction(payload)
            chunk_pairs: list[tuple[str, dict]] = [(doc_text, metadata)]

        elif source_type == "journal_entry":
            raw_content = payload.get("content", "")
            raw_chunks = chunk_text(
                raw_content,
                chunk_size=settings.rag_chunk_size,
                overlap=settings.rag_chunk_overlap,
            )
            chunk_pairs = [_format_journal(payload, c) for c in raw_chunks]

        elif source_type == "mood_entry":
            doc_text, metadata = _format_mood(payload)
            chunk_pairs = [(doc_text, metadata)]

        else:
            logger.warning("ingest_unknown_source_type", source_type=source_type)
            return

        # Embed all chunks in one HTTP call
        texts = [content for content, _ in chunk_pairs]
        embeddings = await _embed_texts(texts, mode="passage")

        async with db_session_factory() as db:
            await _upsert_chunks(db, user_id, source_type, source_id, chunk_pairs, embeddings)

        logger.info(
            "ingest_done",
            source_type=source_type,
            source_id=str(source_id),
            chunks=len(chunk_pairs),
        )

    except Exception:
        logger.exception(
            "ingest_failed",
            source_type=source_type,
            source_id=str(source_id),
        )
