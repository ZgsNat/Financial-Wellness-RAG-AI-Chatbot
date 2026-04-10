"""
Recursive/structural text chunking.

Strategy (per planning doc):
  1. Split by "\\n\\n" (paragraph boundary)
  2. If a paragraph > chunk_size tokens: split by ". " (sentence)
  3. Apply overlap between consecutive chunks

Token counting: approximate via len(text.split()) * 1.3
(avoid loading a real tokenizer — overhead not worth it for this data scale)
"""


def _token_estimate(text: str) -> int:
    """Rough token count: words * 1.3 (accounts for subword splits)."""
    return int(len(text.split()) * 1.3)


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 64,
) -> list[str]:
    """
    Recursively chunk *text* into segments of at most *chunk_size* tokens
    with *overlap* token overlap between consecutive chunks.

    Returns a list of chunk strings (at least one element even for empty input).
    """
    if not text.strip():
        return [text] if text else []

    # Step 1: split by paragraph
    paragraphs = [p for p in text.split("\n\n") if p.strip()]

    # Step 2: further split large paragraphs by sentence
    segments: list[str] = []
    for para in paragraphs:
        if _token_estimate(para) <= chunk_size:
            segments.append(para)
        else:
            sentences = para.split(". ")
            segments.extend(s.strip() for s in sentences if s.strip())

    if not segments:
        return [text]

    # Step 3: merge small segments and apply overlap
    chunks: list[str] = []
    current_tokens: list[str] = []
    current_size = 0

    def _flush() -> None:
        if current_tokens:
            chunks.append(" ".join(current_tokens).strip())

    for seg in segments:
        seg_size = _token_estimate(seg)

        if current_size + seg_size > chunk_size and current_tokens:
            _flush()
            # Carry overlap: take last *overlap* token-worth of words from current
            overlap_words: list[str] = []
            overlap_count = 0
            for word in reversed(" ".join(current_tokens).split()):
                if overlap_count >= overlap:
                    break
                overlap_words.insert(0, word)
                overlap_count += 1
            current_tokens = overlap_words
            current_size = _token_estimate(" ".join(current_tokens))

        current_tokens.append(seg)
        current_size += seg_size

    _flush()
    return chunks if chunks else [text]
