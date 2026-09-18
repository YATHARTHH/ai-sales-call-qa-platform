# SalesCall QA Platform — Project Guidelines & Web Verification Rule

## Mandatory Instruction: Always Verify Technical & Compliance Details via Web

When working on this codebase:

1. **Verify Library Signatures & Versions:**
   - Always verify current API signatures, syntax, and package compatibility for FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, MinIO SDK, Redis/arq, and React/Vite using live web search.
   - Do not assume outdated syntax or hallucinate non-existent arguments.

2. **Australian Regulatory & Compliance Accuracy:**
   - All compliance checks (DMO/VDO statements, Explicit Informed Consent / EIC, ACMA Do Not Call register, AER Energy Retail Code) must match real Australian regulatory standards.
   - Check verbatim text, disclosure obligations, and PCI-DSS card redaction boundaries against authoritative sources.

3. **Deterministic Evaluation Standards:**
   - Ensure all math, rate comparison formulas (e.g., peak/off-peak c/kWh vs supply charge daily rates), and checksum algorithms (Luhn for PCI card detection) are verified.

4. **Principle: "AI Proposes; Deterministic Policy Decides":**
   - Every rule, gate threshold, and confidence score boundary must be deterministic and auditable.
