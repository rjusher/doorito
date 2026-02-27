# PEP 0019: Operational Guardrails and Cleanup

| Field | Value |
|-------|-------|
| **PEP** | 0019 |
| **Title** | Operational Guardrails and Cleanup |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0009, PEP 0017 |

---

## Problem Statement

Without operational controls, the ingest portal can accumulate stale upload sessions, orphaned temp parts, and failed outbox events. Storage can leak, sessions can remain in limbo indefinitely, and there is no visibility into system health. These operational gaps need guardrails and automated cleanup mechanisms.

## Proposed Solution

Add configurable operational settings, automated cleanup jobs, and health endpoints.

### Configurable Settings

- `PORTAL_MAX_FILE_SIZE` — Maximum allowed file size in bytes
- `PORTAL_CHUNK_SIZE` — Default chunk size for upload sessions
- `PORTAL_CHUNK_SIZE_MIN` / `PORTAL_CHUNK_SIZE_MAX` — Chunk size bounds
- `PORTAL_SESSION_TTL_HOURS` — Hours before a stale session is considered expired
- `PORTAL_OUTBOX_BASE_DELAY_SECONDS` — Base delay for exponential backoff
- `PORTAL_OUTBOX_MAX_DELAY_SECONDS` — Maximum backoff delay cap
- `PORTAL_OUTBOX_MAX_ATTEMPTS` — Maximum retry attempts before giving up
- `PORTAL_RUNNER_ENDPOINT` — URL of the AI runner event receiver
- `PORTAL_RUNNER_AUTH_SECRET` — Authentication secret for runner endpoint

### Cleanup Job

A periodic Celery task that:

1. **Mark stale sessions** — Sessions in INIT or IN_PROGRESS state past their TTL are marked FAILED or ABORTED
2. **Delete orphan temp parts** — Temp storage entries whose sessions are COMPLETE, FAILED, or ABORTED
3. **Prune old FAILED sessions** (optional) — Delete sessions that have been FAILED for longer than a retention period

### Health Endpoints

- `GET /health` — Basic liveness check (returns 200 if the app is running)
- `GET /ready` — Readiness check (verifies DB connectivity and storage backend availability)

### Logging

- Structured logs for major transitions: session created, part received, file stored, event dispatched, event delivery failed
- Log format consistent with existing project logging configuration

## Rationale

Operational guardrails are essential for running the ingest portal reliably in production. Configurable limits prevent abuse. Cleanup jobs prevent resource leaks. Health endpoints enable integration with container orchestrators (Kubernetes, Docker health checks). Structured logging provides observability without external monitoring infrastructure.

## Alternatives Considered

### Alternative 1: Manual cleanup only

- **Description**: Rely on admin or management commands for cleanup.
- **Pros**: Simpler implementation.
- **Cons**: Requires manual intervention. Easy to forget. Storage leaks accumulate silently.
- **Why rejected**: Automated cleanup is essential for unattended operation.

### Alternative 2: External monitoring (Prometheus + Grafana)

- **Description**: Add Prometheus metrics and Grafana dashboards for operational visibility.
- **Pros**: Industry-standard observability stack.
- **Cons**: Adds significant infrastructure dependencies. Over-engineered for an OSS portal.
- **Why rejected**: Health endpoints and structured logging provide sufficient observability for the current scale. Prometheus/Grafana can be added later if needed.

## Impact Assessment

### Affected Components

- **Settings**: New portal configuration values in `boot/settings.py`
- **Tasks**: New cleanup periodic task
- **Views**: New health/ready endpoints
- **Services**: Cleanup service for session and temp part management

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking

### Performance Impact

- Cleanup job runs periodically — configurable interval, bulk operations
- Health endpoints are lightweight queries

## Out of Scope

- Prometheus metrics export
- Rate limiting per user/IP
- Alerting (email, Slack, PagerDuty)
- Admin bulk operations UI
- Auto-scaling based on upload queue depth

## Acceptance Criteria

- [ ] Stale sessions (past TTL) are automatically marked FAILED/ABORTED by cleanup job
- [ ] Temp storage is not leaking (orphan parts are deleted after session completion/failure)
- [ ] Readiness endpoint fails when storage backend or database is unavailable
- [ ] All configurable settings have sensible defaults
- [ ] Health endpoint returns 200 when the app is running
- [ ] Structured logs emitted for session creation, part upload, file stored, event dispatched
- [ ] Cleanup job runs on configurable interval via celery-beat

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
