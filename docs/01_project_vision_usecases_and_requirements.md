# SalesCall QA Platform: Project Vision, Use Cases, & Requirements

Welcome to the **SalesCall QA Platform** documentation suite! This document explains **why we built this platform**, the critical industry challenges it solves for Australian energy and broadband telesales, how it enforces strict regulatory compliance, and how it combines deterministic policy rules with AI evaluation—step by step.

---

## 💡 Why We Built SalesCall QA: The Origin Story & Problem Statement

### The Telesales & Compliance Challenge
In regulated industries like **Australian Energy** (Electricity & Gas retail under AER, DMO/VDO rules) and **Telecommunications** (Broadband/Internet sales under ACMA), telesales calls are subject to rigorous legal disclosures. 

During every sales interaction, agents must accurately disclose:
1. **Explicit Informed Consent (EIC)**: Explicit verbal agreement with unambiguous record keeping.
2. **Tariff & Price Comparisons**: Exact percentage variance against the Default Market Offer (DMO) or Victorian Default Offer (VDO) reference prices, daily supply charges ($/day), and peak/off-peak usage rates (c/kWh).
3. **Cooling-off Period Disclosures**: Clear statements regarding mandatory 10-business-day cancellation rights.
4. **PCI-DSS Compliance**: Immediate redaction of sensitive payment card information (PAN numbers) spoken or keyed during call transfers.

### Why Traditional Human QA Auditing Fails

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           TRADITIONAL MANUAL QA vs AUTOMATED QA PLATFORM                         │
├──────────────────────────┬─────────────────────────────────────┬────────────────────────────────┤
│ Metric / Aspect          │ Traditional Manual QA               │ SalesCall QA Platform (Econnex)│
├──────────────────────────┼─────────────────────────────────────┼────────────────────────────────┤
│ Audit Sampling Rate      │ 1% – 3% of total call volume         │ 100% of all call volume        │
│ Feedback Turnaround      │ 3 to 7 days post-call               │ Near real-time (< 3 seconds)   │
│ Consistency & Objectivity│ Subjective per auditor (~65% agreement)│ Deterministic policy (100% reproducible)│
│ PCI-DSS Card Detection   │ Manual mute / high leak risk        │ In-flight Luhn checksum redaction│
│ Regulatory Fine Exposure │ High (undetected systemic errors)   │ Zero-tolerance gate alerts     │
└──────────────────────────┴─────────────────────────────────────┴────────────────────────────────┤
```

---

## 🎯 The 5 Core Problems Solved

```text
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                  THE 5 CORE PROBLEMS SOLVED                                     │
├────────────────────────────┬───────────────────────────────────┬────────────────────────────────┤
│ Real-World Telesales Issue │ Why Existing Tools Fail           │ How SalesCall QA Solves It     │
├────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
│ 1. 97%+ Unaudited Calls    │ Manual listening cannot scale     │ Automated transcription + async│
│    Compliance Blindspot    │ economically.                     │ ARQ worker pipeline.           │
├────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
│ 2. Hallucinating AI        │ Plain LLM scoring hallucinates    │ "AI Proposes; Deterministic    │
│    Evaluators              │ scores and passes non-compliant   │ Policy Decides" Gate Engine.   │
│                            │ calls.                            │                                │
├────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
│ 3. PCI-DSS Card &          │ Transcripts persist spoken credit │ Built-in Luhn checksum card    │
│    PII Leakage             │ card numbers to database.         │ number & PII regex sanitizer.  │
├────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
│ 4. Complex Tariff Math     │ LLMs fail at precise c/kWh rate   │ Python Factual Evaluator with  │
│    Misquoting              │ comparison math against DMO/VDO.  │ exact financial math formulas. │
├────────────────────────────┼───────────────────────────────────┼────────────────────────────────┤
│ 5. Audit Traceability &    │ Audit logs are overwritten or     │ Immutable snapshot JSON +      │
│    Adjudication Conflict   │ lack reproducible context.        │ Lease-fenced Human Review UI.  │
└────────────────────────────┴───────────────────────────────────┴────────────────────────────────┘
```

---

## 🏛️ Australian Regulatory Compliance Framework

The SalesCall QA Platform natively enforces Australian statutory standards across two primary verticals:

### 1. Energy Retailers (AER & Energy Retail Code)
* **Explicit Informed Consent (EIC)**: Verifies mandatory disclosures prior to contract submission.
* **DMO / VDO Reference Price Matching**: Validates quoted rates against official AER benchmarks:
  $$\text{DMO Variance \%} = \frac{\text{Quoted Annual Cost} - \text{DMO Reference Cost}}{\text{DMO Reference Cost}} \times 100$$
* **Dual-Fuel Disclosures**: Ensures gas and electricity terms are individually acknowledged.

### 2. Broadband & Telecommunications (ACMA & TCP Code)
* **Standard Telephone Service (STS) Disclosures**: Clear speed tier explanations (NBN 50 vs NBN 100).
* **Do Not Call (DNC) Register Compliance**: Confirms outbound call authorization timestamps against ACMA lists.

---

## 📊 Core Performance Metrics & Success Criteria

| Objective | Target Benchmark | Verification Mechanism |
| :--- | :--- | :--- |
| **Audit Precision** | ≥ 99.2% | Measured against Gold-Set evaluation benchmarks (`scripts/measure_accuracy.py`) |
| **Pipeline Latency** | < 3.0s per 10-min call | Async ARQ worker execution with Whisper transcription |
| **Policy Determinism** | 100% reproducible | `input_snapshot_json` exact rerun correlation tests |
| **PCI Redaction Accuracy** | 100% Luhn-valid card removal | Unit tests on transcript ingestion pipeline |

---

> [!NOTE]
> Proceed to **[Document 02: System Architecture & Tech Stack](file:///d:/ai-sales-call-qa-platform/docs/02_system_architecture_and_tech_stack.md)** to examine the full technology stack and Architecture Decision Records (ADRs).
