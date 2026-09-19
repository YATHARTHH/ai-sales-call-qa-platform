# AI Sales Call QA & Post-Sale Compliance Platform

> **Score the sale before it ships.**
> Automated post-call compliance scoring for regulated Australian energy and telco sales. Every
> sale is checked against its retailer's checklist before it can submit. All green, it ships
> untouched. Any red, it is held — with the failing criterion, the transcript line, the audio
> timestamp, and the rule version that was live on the call date sitting next to it.

---

## Design principle: *AI proposes; deterministic policy decides*

Every gate decision is made by a deterministic policy engine over an immutable, hashed snapshot of
its inputs. A language model is used in exactly one place — adjudicating findings the rule engine
marked ambiguous — and its proposal is never allowed to loosen a critical outcome. See
[docs/architecture.md](docs/architecture.md).

---

## What it does

**Ingestion — zero manual handling.** The dialler pushes audio by API (`POST /api/v1/recordings/upload`
or `/ingest` for pre-staged object storage). Audio becomes an immutable SHA-256 artifact,
deduplicated on content hash, then transcribed with word-level timestamps and **real speaker
separation**. Diarization uses per-channel energy separation, which is exact when the dialler
records each party on its own channel; mono audio is reported honestly as *not diarized* rather
than labelled as one speaker.

**Three tiers of checks**, all running end-to-end against a 30-check retailer checklist
([`energy_retailer_v1.py`](packages/evaluation/checklists/energy_retailer_v1.py)):

| Tier | Compares | Blocks the sale |
|---|---|---|
| **A · Verbatim** | Transcript vs approved script — recording disclosure, EIC, DMO/VDO, cooling-off, T&Cs, life support | Yes, if critical |
| **B · Factual** | Transcript vs CRM vs rate card — rate, supply charge, email, name, DOB, address, NMI/MIRN, fuel type, concession, life support, move-in date, gift card | Yes |
| **C · Behaviour** | Transcript only — dead air, interruptions, talk ratio, objection handling, speech rate | No |

**No expected value is ever hardcoded.** Each factual check names the CRM path it reads from. If
that value cannot be resolved the check returns `NOT_EVALUABLE` and the gate holds the sale — it
never compares speech against a fabricated default.

**Gate logic.** An 11-condition precedence table: all criticals pass → auto-submit; any critical
fail → held to the TL queue; low confidence or ambiguity on a critical → routed to QA; and 5% of
otherwise-clean calls are deterministically sampled to a human anyway, so the model is measured
rather than trusted.

**Traceability.** Every score resolves to a transcript segment, an audio timestamp, and the exact
`CheckVersion` in force on the call date — resolved by effective-date, not by today's rules.

---

## Scoring accuracy

Accuracy is measured, not asserted. A labelled calibration set
([`energy_gold_set_v1.json`](tests/fixtures/gold/energy_gold_set_v1.json)) records the verdict a
human auditor gave for each check on each call; the harness runs the real orchestrator over it.

```bash
python scripts/measure_accuracy.py                       # print the report
python scripts/measure_accuracy.py --json out.json       # machine-readable
python scripts/measure_accuracy.py --fail-under 0.95     # gate CI on it
```

Current result on `energy-gold-v1` (14 calls, 51 labelled checks):

| Metric | Value |
|---|---|
| **Critical false-passes** | **0** |
| Critical false-fails | 0 |
| Check agreement with auditors | 100% |
| Gate decision agreement | 100% |

The headline number is *critical false-passes* — a critical check the engine passed and a human
failed. It must be zero. [`test_accuracy_regression.py`](tests/integration/test_accuracy_regression.py)
enforces that on every test run.

---

## Dashboards

Aggregation runs server-side over the requested window
(`GET /api/v1/analytics/dashboard`), so figures are correct over the whole period rather than over
whatever page the UI last loaded: first-pass yield, critical fail rate, score **with and without
fatal factors**, which specific check is failing, repeat offences (the same critical check failing
3+ times for one agent in a rolling 7 days, flagging the TL), and auditor agreement rate. Rolled up
daily/weekly/monthly and by agent, team lead, campaign, channel and retailer.

---

## Guardrails

- **Test data only** — all seeded leads, transcripts and identifiers are synthetic.
- **Consent is a check, not an assumption** — the recording disclosure is verified on every call.
- **No card data surfaced** — Luhn-validated PAN redaction is applied at the read boundary, so a
  card number never leaves the API.
- **No advice, no auto-correction** — the system reports what failed and where; it never rewrites
  a sale or contacts a customer.
- **Scored against the rules that were live** — checks resolve to the version effective on the
  call date.
- **Overrides are logged** — a human overturning the gate is recorded with an audit event and an
  outbox message, never silently dropped.

---

## Tech stack

- **API**: Python 3.13 · FastAPI · Pydantic v2
- **Persistence**: PostgreSQL · SQLAlchemy 2.0 (async) · Alembic
- **Queue & transport**: Redis (arq) · transactional outbox with HMAC-signed CRM dispatch
- **Object storage**: MinIO / S3
- **Speech**: faster-whisper (optional extra) · channel-energy diarization
- **Adjudication**: Claude via the Anthropic SDK (optional extra), ambiguous findings only
- **Frontend**: React · Vite · TypeScript · Lucide

Optional extras are genuinely optional — without them the deterministic transcription adapter and a
no-op adjudicator are used, and ambiguity routes to a human.

```bash
pip install -e ".[dev]"            # core + tests
pip install -e ".[dev,speech,llm]" # plus live ASR and AI adjudication
```

---

## Running it

```bash
make up                     # Postgres, Redis, MinIO, API, worker
make migrate                # apply schema
python scripts/seed_data.py # retailers, checklist, and the Lead 3613790 demo call
make test                   # 240 tests
```

The seeded demo reproduces the brief's worked example: Lead 3613790 is **HELD**, with 25 checks
passing and three findings —

```
✕ FACTUAL_PEAK_RATE    (critical)  CRM 31.9c/kWh vs "28.6 cents" heard at 14:02
✕ FACTUAL_EMAIL_ADDRESS (critical) CRM john.smith@gmail.com vs "gmial.com" heard at 22:10
– BEHAVIOUR_DEAD_AIR   (note)      47 seconds of silence at 18:33
```

---

## Documentation

- [Architecture](docs/architecture.md) — topology, state machines, evaluation pipeline
- [Dependency rules](docs/dependency-rules.md) — layer boundaries, enforced by `tests/arch/`
- [Local development](docs/local-development.md)
- [ADR 0001](docs/adr/0001-modular-monolith.md) — modular monolith
