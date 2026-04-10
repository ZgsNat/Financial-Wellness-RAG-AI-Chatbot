FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app
COPY pyproject.toml .

# Step 1: install torch CPU-only first (from PyTorch CPU wheel index).
# Must be a separate step — if we mix indexes, uv resolves CUDA torch from PyPI.
RUN uv venv && \
    uv pip install --no-cache "torch>=2.2.0" \
      --index-url https://download.pytorch.org/whl/cpu

# Step 2: install the rest of the project deps (torch already satisfied, won't re-download CUDA).
RUN uv pip install --no-cache -e .

# Pre-download BGE-M3 into the image layer (~2.2 GB).
# Build is slow once; subsequent rebuilds hit Docker cache.
RUN /app/.venv/bin/python -c \
    "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"

COPY src/ src/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

FROM base AS runtime
EXPOSE 8080
CMD ["uvicorn", "embedding.main:app", "--host", "0.0.0.0", "--port", "8080"]
