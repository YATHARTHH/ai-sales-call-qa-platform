# Architecture Overview — SalesCall QA Platform

## Core Design Philosophy: *"AI Proposes; Deterministic Policy Decides"*

The SalesCall QA platform enforces automated quality assurance and regulatory compliance for sales calls. The system ensures that:
1. **Raw call recordings are immutable source artifacts** tagged with SHA-256 content hashes.
2. **ASR and AI evaluators propose findings** with confidence scores and exact transcript spans.
3. **Deterministic policy engines make the gate decision** (`PASS`, `HOLD`, or `REVIEW_REQUIRED`).
4. **Every result is traceable** to the exact transcript line, audio timestamp, and the check rule version live on the call date.

---

## High-Level Topology

```mermaid
flowchart TD
    A[Dialler / Synthetic Ingestion] --> B[FastAPI Gateway]
    B -->|Immutable Artifact + Hash| C[(PostgreSQL: Durable Job State)]
    B -->|Dispatch Task| D[(Redis Transport)]
    D --> E[Async Worker Daemon]
    
    subgraph E [Worker Pipeline]
        E1[MinIO Audio Fetch] --> E2[Transcription Port]
        E2 --> E3[Multi-Tier Evaluation Port]
        E3 --> E4[Evidence Extraction]
        E4 --> E5[Deterministic Policy Engine]
    end
    
    E5 -->|Gate: AUTO-PASS| F[Auto-Submit to CRM]
    E5 -->|Gate: HOLD| G[Team Lead Queue]
    E5 -->|Gate: REVIEW| H[Human QA Queue]
    
    G & H --> I[SalesCall QA Review UI]
    I -->|Logged Override| F
```

---

## State Machine Separation

| Machine | States | Responsibility |
| :--- | :--- | :--- |
| **PipelineStatus** | `RECEIVED` → `INGESTING` → `TRANSCRIBING` → `TRANSCRIBED` → `EVALUATING` → `EVALUATED` (or `FAILED`) | Tracks operational system progress |
| **GateStatus** | `PENDING` → `PASSED` \| `HELD` \| `REVIEW_REQUIRED` \| `CANCELLED` | Governs compliance business outcome |
