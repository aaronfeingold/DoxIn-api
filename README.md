# Case Study Invoice Extraction API

Flask-based REST API for document processing and invoice management with PostgreSQL and Redis support.

## Overview

This API provides document processing capabilities using LLM-powered invoice extraction, complete CRUD operations for invoice management, and background processing with real-time updates via WebSockets.

## Development Setup

### Prerequisites

- Python 3.11+
- Poetry for dependency management
- Docker and Docker Compose for services

### Quick Start

1. **Start required services**
   ```bash
   cd ../docker
   docker-compose up -d postgres redis
   ```

2. **Set up Python environment**
   ```bash
   # Install dependencies
   poetry install

   # Create environment file
   cp ../.env.template .env
   # Edit .env with your configuration (see Environment Variables section)
   ```

3. **Initialize database**
   ```bash
   poetry run flask init-db
   ```

4. **Run the API**
   ```bash
   poetry run python app.py
   ```

The API will be available at `http://localhost:5000`

### Environment Variables

Create a `.env` file in this directory with the following required variables:

```env
# Database
DATABASE_URL=postgresql://case-study:password@localhost:5433/case-study

# Flask
FLASK_ENV=development
DEBUG=true
SECRET_KEY=your-secret-key-here

# AI Services (required for document processing)
OPENAI_API_KEY=your-openai-api-key

# Redis (optional - for background processing)
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# File uploads
UPLOAD_FOLDER=./uploads
MAX_CONTENT_LENGTH=16777216

# CORS
FRONTEND_URL=http://localhost:3000
```

See the main backend README for complete environment configuration details.

## Project Structure

```
app/
├── routes/           # API route handlers
├── models/           # Database models
├── services/         # Business logic
└── utils/           # Utility functions

tests/               # Test files
├── test_invoice_routes.py
├── test_llm_integration.py
└── test_refactored_services.py
```

## API Documentation

For detailed API endpoint documentation, see:
- `/backend/docs/api-endpoints.md` - Complete API reference
- Health check: `GET /health`
- API base path: `/api/`

## Testing

Run tests using pytest:

```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/test_invoice_routes.py

# Run with coverage
poetry run pytest --cov=app
```

## Background Processing

The API supports background document processing using Celery. Start a worker:

```bash
poetry run celery -A app.services.background_processor.celery_app worker --loglevel=INFO
```

## Production Deployment

For production deployment instructions, see the main backend README and deployment documentation in `/backend/docs/`.

## Troubleshooting

### Database Connection Issues

```bash
# Test database connection
poetry run python -c "from app import create_app, db; app=create_app(); app.app_context().push(); print(db.engine.url)"

# Check if containers are running
docker ps
```

### Common Development Issues

1. **Port conflicts**: Ensure ports 5433 (PostgreSQL) and 6379 (Redis) are available
2. **Environment variables**: Verify `.env` file exists and contains required variables
3. **Dependencies**: Run `poetry install` if you encounter import errors

For additional troubleshooting, check the logs:
```bash
# Docker container logs
docker-compose logs postgres
docker-compose logs redis

# API logs (when running locally)
poetry run python app.py
```