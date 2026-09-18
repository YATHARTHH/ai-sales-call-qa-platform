# Local Development Guide

## Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Make (optional, can run commands directly)

## Getting Started

1. **Clone and configure environment:**
   ```bash
   cp .env.example .env
   ```

2. **Start Docker infrastructure:**
   ```bash
   docker compose up -d
   ```
   *Starts PostgreSQL (5432), Redis (6379), MinIO (9000/9001), API (8000), and Worker.*

3. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

4. **Verify test suite:**
   ```bash
   pytest tests/
   ```

5. **Run the worker smoke test:**
   ```bash
   python scripts/smoke_test.py
   ```
