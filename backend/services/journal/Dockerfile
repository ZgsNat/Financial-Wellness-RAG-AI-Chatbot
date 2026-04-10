FROM python:3.12-slim AS base
RUN pip install uv
WORKDIR /app
COPY pyproject.toml .
RUN uv venv && uv pip install --no-cache -e .
COPY src/ src/
COPY alembic.ini .
COPY migrations/ migrations/
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

FROM base AS runtime
EXPOSE 8000
CMD ["uvicorn", "journal.main:app", "--host", "0.0.0.0", "--port", "8000"]