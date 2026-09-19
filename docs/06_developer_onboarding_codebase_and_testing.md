# SalesCall QA Platform Developer Onboarding, Codebase Map, & Testing Guide

Welcome to **Document 06**! This document provides complete step-by-step developer onboarding instructions, repository file layouts, environment configuration, and test suite execution commands.

---

## 🚀 1. Quick-Start Developer Setup

### Prerequisites
* **Python**: Version `3.11` or higher
* **Node.js**: Version `18.0` or higher (with `npm`)
* **Docker & Docker Compose** (Optional for local PostgreSQL & MinIO)

### Step 1: Clone & Environment Setup
```bash
git clone https://github.com/YATHARTHH/ai-sales-call-qa-platform.git
cd ai-sales-call-qa-platform

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
source .venv/bin/activate

# Install Python dependencies in editable mode
pip install -e .
```

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Key environment settings:
```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/salescall_qa
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

### Step 3: Frontend Web Setup
```bash
cd apps/web
npm install
npm run dev
```

---

## 📁 2. Codebase Map & Repository Layout

```text
ai-sales-call-qa-platform/
├── apps/
│   ├── api/                      # FastAPI Backend Gateway
│   │   ├── main.py               # FastAPI application entry point
│   │   ├── middleware.py         # CORS & Auth middleware
│   │   └── routers/              # API Endpoints (recordings, evaluations, analytics, events)
│   ├── web/                      # React 18 + Vite Frontend SPA
│   │   ├── src/
│   │   │   ├── components/       # UI Components (LiveStreamMonitor, AnalyticsDashboard, etc.)
│   │   │   ├── api/              # Axios/Fetch REST client modules
│   │   │   └── App.tsx           # Main application routing
│   │   └── vite.config.ts        # Vite build configuration
│   └── worker/                   # Async ARQ Background Processing Worker
│       └── tasks.py              # Transcription & evaluation worker tasks
├── packages/
│   ├── contracts/                # Pydantic v2 schemas and DTO contracts
│   ├── domain/                   # Core business domain entities
│   ├── evaluation/               # Policy Gate & Rule Evaluation Engine
│   │   ├── evaluators/           # Verbatim, Factual, & Behavior evaluators
│   │   └── policy/               # Gate Engine & Adjudication policies
│   └── infrastructure/           # Database repositories, MinIO S3, & LLM adapters
├── scripts/                      # Utility scripts (seed_data, batch_qa, measure_accuracy)
├── tests/
│   ├── fixtures/                 # Gold-Set evaluation datasets
│   ├── integration/              # E2E pipeline & API integration tests
│   └── unit/                     # Unit test suite for policy gates & evaluators
├── Makefile                      # Command shortcuts
└── pyproject.toml                # Python project dependencies & tooling config
```

---

## 🧪 3. Running the Test Suite

The repository features comprehensive unit, integration, and accuracy regression tests:

```bash
# Run complete pytest test suite
pytest

# Run unit tests only
pytest tests/unit/

# Run integration tests only
pytest tests/integration/

# Run Gold-Set accuracy measurement script
python scripts/measure_accuracy.py
```

---

> [!NOTE]
> Proceed to **[Document 07: Deployment & SRE](file:///d:/ai-sales-call-qa-platform/docs/07_deployment_cicd_scalability_and_sre.md)** for production deployment specifications.
