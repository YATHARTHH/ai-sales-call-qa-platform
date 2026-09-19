# SalesCall QA Platform API, Events, & Integration Reference

Welcome to **Document 08**! This document provides the complete API reference, WebSocket/SSE event streaming specifications, and transactional outbox webhook event schemas.

---

## 1. REST API Endpoint Reference

### 1. Upload Call Recording
* **URL**: `POST /api/v1/recordings/upload`
* **Content-Type**: `multipart/form-data`
* **Request Form Fields**:
  * `file`: Audio binary (`.wav`, `.mp3`)
  * `tenant_id`: String (`econnex_01`)
  * `external_call_id`: String (`CALL-99201`)
* **Response (201 Created)**:
  ```json
  {
    "call_id": "4b492ed8-df29-4b23-a740-4aca0cbfa1dd",
    "status": "PENDING",
    "audio_s3_key": "recordings/econnex_01/4b492ed8-df29-4b23-a740-4aca0cbfa1dd.wav",
    "created_at": "2026-09-19T10:00:00Z"
  }
  ```

---

### 2. Trigger Batch Call Evaluation
* **URL**: `POST /api/v1/evaluations/batch`
* **Request Body**:
  ```json
  {
    "call_ids": ["4b492ed8-df29-4b23-a740-4aca0cbfa1dd"],
    "checklist_id": "energy_retailer_v1"
  }
  ```
* **Response (202 Accepted)**:
  ```json
  {
    "job_id": "job_8829102",
    "status": "QUEUED",
    "total_calls": 1
  }
  ```

---

### 3. Fetch QA Analytics Dashboard Data
* **URL**: `GET /api/v1/analytics/dashboard`
* **Query Parameters**: `tenant_id=econnex_01&timeframe=7d`
* **Response (200 OK)**:
  ```json
  {
    "total_calls": 1250,
    "pass_rate_percentage": 94.2,
    "gate_distribution": {
      "PASS": 1177,
      "SOFT_FAIL": 45,
      "MANUAL_REVIEW": 18,
      "HARD_FAIL": 10
    },
    "top_failing_rules": [
      {"rule_id": "EIC_VERBAL_DISCLOSURE", "fail_count": 8},
      {"rule_id": "DMO_VARIANCE_QUOTE", "fail_count": 2}
    ]
  }
  ```

---

## 2. Event Streaming & WebSockets

### Live Stream Audit Monitor (WebSocket)
* **URL**: `ws://localhost:8000/api/v1/events/ws/stream/{call_id}`
* **Stream Payload (Server -> Client)**:
  ```json
  {
    "event_type": "TRANSCRIPT_CHUNK",
    "call_id": "demo-call-live-1",
    "speaker": "AGENT",
    "text": "This call is recorded for quality and compliance under AER regulations.",
    "timestamp_ms": 1200,
    "checks": {
      "recording_disclosure": "PASS",
      "explicit_informed_consent": "PENDING"
    }
  }
  ```

---

## 3. Transactional Outbox Webhook Schemas

When an evaluation finishes or an auditor overrides a gate verdict, an outbox event is dispatched to registered CRM webhooks:

### Event: `EVALUATION_COMPLETED`
```json
{
  "event_id": "evt_9918231",
  "event_type": "EVALUATION_COMPLETED",
  "timestamp": "2026-09-19T10:05:00Z",
  "payload": {
    "call_id": "4b492ed8-df29-4b23-a740-4aca0cbfa1dd",
    "tenant_id": "econnex_01",
    "final_gate": "PASS",
    "overall_score": 98.5,
    "requires_human_review": false
  }
}
```

---

> [!NOTE]
> Proceed to **[Document 09: Interview Prep & FAQ](file:///d:/ai-sales-call-qa-platform/docs/09_interview_prep_glossary_and_faq.md)** for deep-dive questions and industry glossary.
