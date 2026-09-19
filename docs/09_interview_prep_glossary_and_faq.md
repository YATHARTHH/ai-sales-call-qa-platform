# SalesCall QA Platform Interview Prep, Compliance Glossary, & FAQ

Welcome to **Document 09**! This document provides architectural interview prep questions, an Australian compliance glossary, and answers to frequently asked engineering and operational questions.

---

## 🎓 1. Architectural Deep-Dive Interview Q&A

### Q1: Why did you implement a deterministic Policy Gate Engine instead of allowing the LLM to directly output final PASS/FAIL verdicts?
**Answer**:
Raw LLM outputs are inherently non-deterministic. In regulated financial and energy markets, a compliance audit verdict must be **100% reproducible and auditable**. If an auditor re-runs an audit, the verdict must not flip from PASS to FAIL due to LLM sampling temperature. Furthermore, legal compliance requires strict rule precedence: if a mandatory Explicit Informed Consent (EIC) rule fails, the call MUST trigger a `HARD_FAIL` regardless of how high the rest of the call scored. We enforce **"AI Proposes; Deterministic Policy Decides"**—evaluators propose scores and confidence, while pure Python code computes the verdict.

---

### Q2: How does the system handle Payment Card Industry (PCI-DSS) data spoken during call recordings?
**Answer**:
Audio files pass through Whisper transcription into text streams, which are immediately processed by an in-flight **PCI-DSS Luhn Redactor** before reaching any database or long-term storage. The redactor uses regular expressions to find 13 to 19 digit sequences and runs the mathematical **Luhn algorithm checksum**. If valid, the digits are overwritten with `[CARD_REDACTED_PCI_DSS]`. Spoken card numbers are never stored in plaintext transcripts.

---

### Q3: How do you guarantee exact audit reproducibility if rules or prompts change in the future?
**Answer**:
Every evaluation run serializes its complete inputs into an immutable JSON blob (`evaluations.input_snapshot_json`) stored in PostgreSQL. This snapshot captures the exact transcript utterances, checklist rule versions, and policy threshold configurations present at evaluation time. Rerunning an audit evaluates this immutable snapshot rather than live DB state.

---

### Q4: How does the system handle high-concurrency auditor overrides without race conditions?
**Answer**:
We use an **Adjudicator Lease** mechanism (`AdjudicatorLease`) with atomic PostgreSQL locks. When an auditor opens a call for review, they acquire an exclusive lease for 300 seconds. If a second auditor attempts to review the same call, the API returns `409 Conflict`.

---

## 📖 2. Australian Compliance & Industry Glossary

| Term | Definition |
| :--- | :--- |
| **AER** | **Australian Energy Regulator**: Federal authority governing national energy market rules and retail compliance. |
| **DMO** | **Default Market Offer**: Statutory reference price cap set annually by the AER for electricity customers in NSW, SA, and SE QLD. |
| **VDO** | **Victorian Default Offer**: Statutory reference price set by the Essential Services Commission (ESC) for Victorian energy customers. |
| **EIC** | **Explicit Informed Consent**: Mandatory statutory disclosure requiring explicit, unambiguous customer consent prior to transferring energy retail contracts. |
| **ACMA** | **Australian Communications and Media Authority**: Regulatory body governing telecommunications, telesales, and the Do Not Call (DNC) Register. |
| **PCI-DSS** | **Payment Card Industry Data Security Standard**: Technical security standard requiring masking of credit card primary account numbers (PAN). |
| **Diarization** | The process of partitioning an audio recording into distinct speaker channels (e.g. Agent vs Customer). |
| **Outbox Pattern** | Architectural pattern guaranteeing reliable event publishing by writing events to a database table within the primary transaction. |

---

## ❓ 3. Frequently Asked Questions (FAQ)

### Q: Can this platform support other telesales industries beyond Energy and Broadband?
**Yes!** The evaluation engine is completely decoupled from domain logic. New checklists (e.g., Insurance, Banking, Automotive sales) can be added simply by creating a new checklist builder class implementing `BaseChecklist`.

### Q: What happens if the primary LLM API goes down during evaluation?
The system incorporates an automatic **Fallback Provider Pattern**. If Claude 3.5 Sonnet fails or times out, the adjudicator automatically routes the request to Gemini 2.5 Flash.

---

> [!TIP]
> You have completed the 9-part documentation suite! Return to **[Document 01: Project Vision](file:///d:/ai-sales-call-qa-platform/docs/01_project_vision_usecases_and_requirements.md)** or view the main **[README.md](file:///d:/ai-sales-call-qa-platform/README.md)**.
