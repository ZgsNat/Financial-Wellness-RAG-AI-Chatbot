"""
Hybrid retrieval — Phase 3.

Combines pgvector cosine similarity (semantic) with PostgreSQL ts_rank (lexical)
using a weighted sum:

    hybrid_score = VECTOR_WEIGHT × vector_score + BM25_WEIGHT × bm25_score

Why hybrid:
- Pure vector: finds semantically similar chunks but cannot distinguish exact
  amounts, dates, or category names — journal narratives often out-score
  short transaction records even when the user asks for specific data.
- BM25 / ts_rank: exact keyword matching that rewards chunks containing the
  precise words the user typed (e.g. "sức khỏe", "thuốc", "mua sắm").
- Combined: transaction chunks with an exact category match AND semantic
  relevance now score higher than journal entries about the same topic.

Multi-tenant isolation (WHERE user_id = ?) is mandatory — never omit.
"""
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# Blend weights — must sum to 1.0
# 0.6 / 0.4 chosen empirically; eval_rag.ps1 is used to verify.
VECTOR_WEIGHT: float = 0.6
BM25_WEIGHT: float = 0.4


@dataclass
class RetrievedChunk:
    content: str
    source_type: str
    source_id: uuid.UUID
    similarity: float       # hybrid score (0–1), reported to context_builder
    metadata: dict


async def retrieve_chunks(
    db: AsyncSession,
    user_id: uuid.UUID,
    query_vector: list[float],
    query_text: str = "",
    top_k: int = 8,
    source_types: list[str] | None = None,
) -> list[RetrievedChunk]:
    """
    Return top-k chunks by hybrid score for *user_id*.

    Parameters
    ----------
    query_vector : embedding of the query (produced by embedding service)
    query_text   : raw query string used for BM25 ts_rank scoring.
                   Falls back to pure vector search when empty.
    top_k        : number of results to return
    source_types : if provided, restrict to these source_type values only
    """
    vector_literal = f"[{','.join(str(v) for v in query_vector)}]"

    # Optional source_type filter clause
    type_filter = ""
    if source_types:
        quoted = ", ".join(f"'{t}'" for t in source_types)
        type_filter = f"AND source_type IN ({quoted})"

    if query_text.strip():
        # ── Hybrid mode ───────────────────────────────────────────────────────
        # plainto_tsquery converts free text to tsquery without requiring
        # special syntax.  'pg_catalog.simple' matches the index dictionary.
        sql = text(
            f"""
            SELECT
                content,
                source_type,
                source_id,
                metadata,
                (
                    {VECTOR_WEIGHT} * (1 - (embedding <=> :query_vector ::vector))
                  + {BM25_WEIGHT}  * ts_rank(fts, plainto_tsquery('pg_catalog.simple', :query_text))
                ) AS similarity
            FROM document_chunks
            WHERE user_id    = :user_id
              AND embedding  IS NOT NULL
              {type_filter}
            ORDER BY similarity DESC
            LIMIT :top_k
            """
        )
        params = {
            "query_vector": vector_literal,
            "query_text": query_text,
            "user_id": str(user_id),
            "top_k": top_k,
        }
    else:
        # ── Pure vector fallback (no query text available) ────────────────────
        sql = text(
            f"""
            SELECT
                content,
                source_type,
                source_id,
                metadata,
                1 - (embedding <=> :query_vector ::vector) AS similarity
            FROM document_chunks
            WHERE user_id   = :user_id
              AND embedding IS NOT NULL
              {type_filter}
            ORDER BY embedding <=> :query_vector ::vector
            LIMIT :top_k
            """
        )
        params = {
            "query_vector": vector_literal,
            "user_id": str(user_id),
            "top_k": top_k,
        }

    result = await db.execute(sql, params)
    rows = result.fetchall()
    chunks = [
        RetrievedChunk(
            content=row.content,
            source_type=row.source_type,
            source_id=uuid.UUID(str(row.source_id)),
            similarity=float(row.similarity),
            metadata=row.metadata or {},
        )
        for row in rows
    ]

    logger.info(
        "retrieved_chunks",
        count=len(chunks),
        user_id=str(user_id),
        mode="hybrid" if query_text.strip() else "vector",
        source_types=source_types,
    )
    return chunks
