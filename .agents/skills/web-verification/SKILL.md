---
name: web-verification
description: >-
  Mandatory skill to verify technical requirements, package versions, API schemas, domain regulations, and architecture choices against the live web using search_web and read_url_content. Use whenever implementing or validating libraries, external APIs, legal/compliance rules, or architectural decisions.
---

# Web Verification & Fact-Checking Skill

This skill enforces a rigorous verification workflow: **Always verify from the live web before assuming, generating, or finalizing technical implementations.**

---

## When to Use This Skill

1. **Third-Party Libraries & APIs:**
   - Verifying modern library versions, syntax, and breaking changes (e.g., SQLAlchemy 2.0 async syntax, Pydantic v2 schemas, FastAPI lifespan events, Vite configs).
   - Checking package availability on PyPI or npm.

2. **Domain & Regulatory Rules:**
   - Australian Energy & Telecom Compliance:
     - **EIC** (Explicit Informed Consent) requirements.
     - **DMO / VDO** (Default Market Offer / Victorian Default Offer) reference price statements.
     - **ACMA Do Not Call (DNC) Register** requirements.
     - **AER** (Australian Energy Regulator) retailer compliance obligations.

3. **Schema & Protocol Standards:**
   - MinIO S3 API signatures, Redis asynchronous queue semantics (arq/Celery), PostgreSQL connection pooling.
   - PCI-DSS card data masking and redaction specifications.

4. **Ambiguous or Critical Facts:**
   - Whenever an implementation choice has multiple competing conventions, search the web to confirm current industry best practices.

---

## Verification Protocol

1. **Search Before Implementing:**
   - Use `search_web` with precise keywords (e.g., `"fastapi async lifespan sqlalchemy 2.0"`, `"australian energy regulator explicit informed consent audio requirements"`).
2. **Fetch Primary Sources:**
   - When documentation URLs are returned, fetch them using `read_url_content` to extract exact syntax or regulatory wording.
3. **Cross-Check with Codebase:**
   - Compare web findings directly with local codebase constraints to ensure seamless compatibility.
4. **Document Source in Code:**
   - Add concise references/comments in code where compliance or external standards are applied (e.g., `# Reference: AER NECF Part 2 Div 4 EIC requirement`).
