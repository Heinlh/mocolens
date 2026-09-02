# Serves the FastAPI backend on Render. The curated analytics DB + vector
# index (data/curated/, ~40MB) are committed to git and baked into the image
# below - Render's free tier has no persistent disk, and re-running the full
# ingestion pipeline (Socrata downloads + Docling + embeddings) on every cold
# start would be slow and fragile for a portfolio MVP. Rebuild+push this repo
# whenever the curated data changes (scripts/build_curated_tables.py, etc.).
#
# Deliberately installs the base package only, NOT the "ingest" extra
# (Docling) - Docling pulls a GPU torch build plus OCR/vision deps that are
# several GB and unused at serve time (it only runs during ingestion, never
# while answering a query). The CPU-only torch install below covers the one
# runtime dependency that still needs it: sentence-transformers, for
# embedding incoming questions against the vector index.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY data/curated ./data/curated

RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2
EXPOSE 10000

# Render injects PORT (10000 by default). Shell form is required here so
# the environment variable is expanded before Uvicorn starts.
CMD ["sh", "-c", "exec uvicorn mocolens.api.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
