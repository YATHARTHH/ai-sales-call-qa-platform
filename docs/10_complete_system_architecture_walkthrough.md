# SalesCall QA Platform Complete System Architecture Walkthrough

Welcome to **Document 10**! This document provides a complete, step-by-step breakdown of all **6 Architectural Modules** and **Supporting Infrastructure** shown in the official SalesCall QA Platform Architecture Diagram.

---

## 📐 Overall System Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                SYSTEM ARCHITECTURE MODULES                                      │
├──────────────┬──────────────────┬─────────────────┬─────────────────┬──────────────┬────────────┤
│ Box 1        │ Box 2            │ Box 3           │ Box 4           │ Box 5        │ Box 6      │
│ Ingestion &  │ Transcription &  │ Async Worker &  │ Policy Gate &   │ Persistence &│ Auditor    │
│ Preprocessing│ Diarization      │ Evaluation      │ Adjudication    │ Outbox       │ Console UI │
└──────────────┴──────────────────┴─────────────────┴─────────────────┴──────────────┴────────────┘
```

---

## 1️⃣ Box 1: Ingestion & Preprocessing

```text
  [Call Audio Upload (.wav/.mp3)] ──► [FastAPI Endpoint] ──► [MinIO S3 Storage] ──► [PCI-DSS Luhn Redactor]
```

### 1. Call Audio Upload (`.wav` / `.mp3`)
* **What happens**: The telephony system (PBX / Dialler) sends raw audio recordings of sales calls to the platform via HTTP multipart upload (`POST /api/v1/recordings/upload`).

### 2. FastAPI Ingestion Endpoint
* **What happens**: Validates tenant credentials (`X-API-Key`), generates a canonical UUID for the call, and enforces a 50MB payload size limit.

### 3. MinIO S3 Object Storage
* **What happens**: Stores raw binary audio in S3 buckets using structured multi-tenant paths:
  `recordings/{tenant_id}/{call_id}.wav`

### 4. PCI-DSS Luhn Redactor & PII Sanitizer
* **What happens**: In-flight mathematical card checksum engine. Scans transcript text using regex and runs the mathematical **Luhn Checksum Algorithm** ($\text{sum} \pmod{10} == 0$).
* **Outcome**: Valid credit card numbers spoken by customers are overwritten with `[CARD_REDACTED_PCI_DSS]` before reaching long-term storage.

---

## 2️⃣ Box 2: Transcription & Diarization

```text
  [Faster-Whisper Adapter] ──► [Speaker Diarizer] ──► [Role Resolver] ──► [Utterance Normalizer]
```

### 1. Faster-Whisper / OpenAI Whisper Adapter
* **What happens**: Converts raw audio soundwaves into text words with exact sub-second start and end timestamps (`start: 1.2s`, `end: 4.5s`).

### 2. Speaker Diarization Engine (Agent vs Customer)
* **What happens**: Partitions audio channels to identify distinct speakers. Uses per-channel energy separation for dual-channel telephony recordings.

### 3. Role Resolver
* **What happens**: Analyzes conversation context, greetings, and speech patterns to assign roles:
  * 👤 **`AGENT`**: *"Hello! This call is recorded for quality and compliance."*
  * 🗣️ **`CUSTOMER`**: *"Hi! Yes, I consent."*

### 4. Utterance Sequence Normalizer
* **What happens**: Assembles timestamp-ordered JSON arrays of clean utterances for evaluation.

---

## 3️⃣ Box 3: Asynchronous Worker & Evaluation Engine

```text
  [Redis + ARQ Task Queue] ──► [Checklist Registry] ──► [3-Tier Evaluators (Verbatim, Factual, Behavior)]
```

### 1. Redis + ARQ Task Queue
* **What happens**: Distributed async task queue that runs heavy transcription and evaluation worker tasks in parallel without blocking API threads.

### 2. Checklist Registry (`EnergyRetailerV1` & `BroadbandRetailerV1`)
* **What happens**: Fetches the active checklist rules for the targeted industry (e.g. 30 rules for Australian Energy retail).

### 3. 3-Tier Evaluators:
* **Verbatim Evaluator**: Uses **Fuzzy Token Matching (Levenshtein Distance)** to verify mandatory legal disclaimers.
* **Factual Evaluator**: Performs exact decimal math comparing quoted rates against Australian Government AER DMO/VDO benchmarks:
  $$\text{DMO Variance \%} = \frac{\text{Quoted Annual Cost} - \text{DMO Reference Price}}{\text{DMO Reference Price}} \times 100$$
* **Behavior Evaluator**: Measures agent speech speed, dead air silences (> 5s), and interruptions.

---

## 4️⃣ Box 4: Deterministic Policy Gate & Adjudication

```text
  [Policy Gate Engine] ──► [Precedence Resolver] ──► [LLM Adjudicator Subsystem] ──► [Lease Manager]
```

### 1. Policy Gate Engine (*"AI Proposes; Deterministic Policy Decides"*)
* **What happens**: Evaluators propose rule scores and confidence values ($s_i, c_i$). The Policy Gate Engine applies pure Python code to compute 100% reproducible legal verdicts.

### 2. Precedence Resolver Hierarchy:
$$\text{HARD\_FAIL} \succ \text{SOFT\_FAIL} \succ \text{MANUAL\_REVIEW} \succ \text{PASS}$$
* 🔴 **`HARD_FAIL`**: Mandatory legal rule failed $\rightarrow$ Score forced to **0%**, sale blocked!
* 🟡 **`SOFT_FAIL`**: Non-mandatory rule failed $\rightarrow$ Points deducted, sale proceeds, agent flagged.
* 🔵 **`MANUAL_REVIEW`**: Confidence $< 0.75$ or 5% random calibration audit $\rightarrow$ Routed to human QA queue.
* 🟢 **`PASS`**: All rules passed cleanly $\rightarrow$ Auto-submitted to CRM!

### 3. LLM Adjudicator Subsystem (Claude 3.5 / Gemini 2.5 Fallback)
* **What happens**: Analyzes ambiguous edge cases ($0.50 \le c_i < 0.75$). Uses **Claude 3.5 Sonnet** as primary provider and **Gemini 2.5 Flash** as fallback.

### 4. Adjudicator Lease Manager
* **What happens**: Grants a 300-second atomic lease lock (`AdjudicatorLease`) in PostgreSQL when a QA auditor opens a call for review, preventing concurrent reviewer collisions.

---

## 5️⃣ Box 5: Persistence & Outbox Event Dispatcher

```text
  [PostgreSQL / Async SQLAlchemy DB] ──► [Transactional Outbox Table] ──► [Outbox Dispatcher Daemon] ──► [CRM Webhooks]
```

### 1. PostgreSQL / Async SQLAlchemy 2.0 DB
* **What happens**: Stores structured call records, transcripts, evaluation trees, and immutable input snapshots (`input_snapshot_json`).

### 2. Transactional Outbox Table (`outbox_events`)
* **What happens**: Every evaluation outcome or human override writes an event record inside the primary database transaction.

### 3. Outbox Dispatcher Daemon
* **What happens**: Asynchronous worker daemon polls outbox events and dispatches webhooks with exponential backoff retries.

### 4. Webhook Delivery & CRM Integration
* **What happens**: Delivers clean JSON payloads to external CRMs (**Salesforce**, **HubSpot**).

---

## 6️⃣ Box 6: Auditor Console & Analytics Portal

```text
  [React 18 + Vite SPA] ──► [Audio-Transcript Sync] ──► [Live Audit Stream Monitor] ──► [Human Review Interface]
```

### 1. React 18 + Vite Glassmorphic Dashboard
* **What happens**: Fast SPA presenting analytics metrics, First-Pass Yield (FPY), critical fail rates, and agent leaderboards.

### 2. Interactive Call Audio & Transcript Sync
* **What happens**: Interactive player synced to transcript lines—clicking any sentence jumps audio playback to that exact second.

### 3. Live Audio Audit Stream Monitor
* **What happens**: Real-time stream monitor displaying audio chunks, speaker badges, instant compliance checks, and animated final verdict banners with a 1.5s local simulation fallback.

### 4. Human Review & Calibration Interface
* **What happens**: Allows QA auditors to inspect held calls, record override rationales, and recalibrate evaluation thresholds.

---

## 🛠️ Supporting Infrastructure

* **Compute & Runtime**: Docker Containers, Python 3.11+, FastAPI 0.115, Redis 7, ARQ Worker Pool.
* **Databases & Storage**: PostgreSQL Primary DB, MinIO S3 Storage, Redis Cache/Queue.
* **External Integrations**: HubSpot CRM, Salesforce CRM, Webhook Dispatcher.
* **Security & Observability**: JWT / RS256 Authentication, PCI-DSS Luhn Compliance, Prometheus & Grafana Monitoring.

---

> [!NOTE]
> Return to **[Document 01: Project Vision](file:///d:/ai-sales-call-qa-platform/docs/01_project_vision_usecases_and_requirements.md)** or view the main **[README.md](file:///d:/ai-sales-call-qa-platform/README.md)**.
