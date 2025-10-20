# Multi-stage build for Flask API
FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Install system dependencies and Poetry
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install poetry

# Configure Poetry - disable virtual environments in Docker
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# Copy poetry files for better caching
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

# Copy application code
COPY . .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

# Expose port
EXPOSE 8000

# Default command (can be overridden)
CMD ["poetry", "run", "gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--worker-class", "gevent", "--worker-connections", "1000", "app:create_app()"]
