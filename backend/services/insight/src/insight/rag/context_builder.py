"""
Context builder: dedup, format, and truncate retrieved chunks.

Context is assembled from RetrievedChunk objects and formatted for the LLM prompt.
"""
from insight.rag.retrieval import RetrievedChunk

# Approximate token budget for assembled context
MAX_CONTEXT_TOKENS = 6000

# Similarity threshold above which two chunks are considered near-duplicates
DEDUP_THRESHOLD = 0.97

# Rough token estimator (same as chunker — words * 1.3)
def _token_estimate(text: str) -> int:
    return int(len(text.split()) * 1.3)


def build_context(chunks: list[RetrievedChunk]) -> tuple[str, list[dict]]:
    """
    Deduplicate, format, and truncate *chunks* into a context string.

    Returns:
        context  — assembled string ready for the system prompt
        sources  — list of source metadata dicts for the response payload
    """
    seen_source_ids: set[str] = set()
    deduped: list[RetrievedChunk] = []

    for chunk in chunks:
        key = str(chunk.source_id)
        if key in seen_source_ids and chunk.similarity > DEDUP_THRESHOLD:
            continue
        seen_source_ids.add(key)
        deduped.append(chunk)

    # Format each chunk as a labelled entry
    lines: list[str] = []
    sources: list[dict] = []
    total_tokens = 0

    for chunk in deduped:
        formatted = f"Source [{chunk.source_type}]: {chunk.content}"
        token_count = _token_estimate(formatted)

        if total_tokens + token_count > MAX_CONTEXT_TOKENS:
            break  # truncate at budget

        lines.append(formatted)
        total_tokens += token_count
        sources.append({
            "source_type": chunk.source_type,
            "source_id": str(chunk.source_id),
            "similarity": round(chunk.similarity, 4),
        })

    return "\n\n".join(lines), sources
