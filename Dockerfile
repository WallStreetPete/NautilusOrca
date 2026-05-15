# syntax=docker/dockerfile:1.7
# Multi-purpose image: defaults to Streamlit console (Railway), overridable for
# paper-trading via CMD.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONIOENCODING=utf-8

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps from requirements.txt (matches pyproject; works on
# Railway, Fly, Render, etc. without uv).
COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy source and editable-install the package
COPY src ./src
COPY config ./config
COPY scripts ./scripts
COPY frontend ./frontend
COPY streamlit_app.py ./
COPY .streamlit ./.streamlit
RUN pip install -e . --no-deps

# Create runtime directories (Railway provides a $RAILWAY_VOLUME_MOUNT_PATH
# for persistent data; we default to local).
RUN mkdir -p /app/data/catalog /app/data/runs /app/data/models /app/data/reports

EXPOSE 8501

# Streamlit reads $PORT from the platform (Railway, Fly, Render set this).
CMD ["sh", "-c", "streamlit run streamlit_app.py --server.port=${PORT:-8501} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
