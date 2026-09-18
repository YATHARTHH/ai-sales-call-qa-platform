# ADR 0001: Modular Monolith with Async Background Workers

## Status
Accepted

## Context
We require a production-grade post-call compliance and QA scoring platform capable of ingesting high volumes of audio, generating transcripts, evaluating multi-tier rules, and presenting auditable evidence with sub-second response times.

## Decision
We adopt a **Modular Monolith with Async Workers (Ports & Adapters)** rather than microservices:
- Single codebase structured into distinct decoupled packages (`domain`, `application`, `infrastructure`, `evaluation`, `contracts`, `observability`).
- Fast HTTP ingestion via FastAPI returning `202 Accepted`.
- Durable job state stored in PostgreSQL.
- Ephemeral asynchronous task transport via Redis.
- Background worker processes executing audio processing and evaluation.

## Consequences
- Fast local development with zero distributed microservice orchestration overhead.
- Clean boundaries guarantee future extraction into independent microservices if required.
