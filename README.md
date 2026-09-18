# AI Sales Call QA & Post-Sale Compliance Platform

> **Score the sale before it ships.**
> An automated post-call compliance verification, verbatim script checker, and audit scoring engine built for CIMET CRM sales validation.

---

## 🚀 Key Features

- **Ingestion Pipeline**: Automated audio & transcript ingestion with speaker diarization and word-level timestamps keyed on Lead ID.
- **Multi-Tier Scoring Engine**:
  - **Tier A (Verbatim / Script)**: Compliance disclaimers, T&Cs, and DMO/VDO read verification.
  - **Tier B (Factual Match)**: Spoken rate vs CRM lead fields vs Retailer rate cards diffing.
  - **Tier C (Behavioral)**: Dead air, silence gaps (>45s), and sentiment analysis.
- **Interactive Audio & Timestamp Console**: Click any check badge or transcript line to jump directly to that exact second (`14:02`, `22:10`).
- **Gate & Escalation Routing**: Auto-pass clean sales, route critical failures to Team Lead queue with exact reasoning.
- **PCI Guardrails**: Automated card data redaction in transcript view.
- **Analytics Dashboard**: First-Pass Yield (FPY), repeat offender warnings, and auditor agreement calibration.

---

## 🛠 Tech Stack

- **Frontend**: React + Vite + TailwindCSS + Lucide Icons
- **Backend**: Node.js / Express API Server
- **Scoring**: Structured LLM & Fuzzy String Alignment Engine
