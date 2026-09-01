# Serves the FastAPI backend on Render. The curated analytics DB + vector
# index (data/curated/, ~40MB) are committed to git and baked into the image
# below - Render's free tier has no persistent disk, and re-running the full
# ingestion pipeline (Socrata downloads + Docling + embeddings) on every cold
# start would be slow and fragile for a portfolio MVP. Rebuild+push this repo
# whenever the curated data changes (scripts/build_curated_tables.py, etc.).
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY data/curated ./data/curated

RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "mocolens.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
