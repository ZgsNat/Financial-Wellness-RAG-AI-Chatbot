"""
BGE-M3 singleton — loaded once at startup, reused for every request.

BGE-M3 uses instruction prefixes to distinguish query-time from passage-time
encoding. The prefixes improve retrieval quality — always include them.
  - query   → "query: <text>"
  - passage → "passage: <text>"
"""
from sentence_transformers import SentenceTransformer

_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        raise RuntimeError("Model not loaded. Call load_model() during startup.")
    return _model


def load_model(model_name: str = "BAAI/bge-m3") -> SentenceTransformer:
    global _model
    _model = SentenceTransformer(model_name)
    return _model
