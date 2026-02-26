# PEP 0004: Event Outbox Infrastructure

| Field | Value |
|-------|-------|
| **PEP** | 0004 |
| **Title** | Event Outbox Infrastructure |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-25 |
| **Updated** | 2026-02-25 |
| **Related PEPs** | PEP 0003 (Extend Data Models — outbox deferred from there) |
| **Depends On** | PEP 0003 |

---

## Problem Statement

Doorito needs a reliable mechanism for delivering domain events (e.g., `file.stored`, `user.created`) to downstream consumers. Without this, event-driven workflows require ad-hoc solutions that risk event loss, duplication, or tight coupling between producers and consumers.

PEP 0003 originally included a `PortalEventOutbox` model in the `uploads` app, but the Design Review identified several problems: the "Portal" prefix was meaningless, placing it in `uploads/` limited reuse, a hard FK to `IngestFile` coupled it to uploads, and defining the schema without a delivery worker meant rows would accumulate forever. The outbox was deferred to this dedicated PEP for a complete design.

## Proposed Solution

Implement a generic transactional outbox in the `common` app. The outbox provides reliable, at-least-once event delivery using the transactional outbox pattern:

1. **`OutboxEvent` model** in `common/models.py` — a self-contained event record using the aggregate/payload pattern (no FK to specific models)
2. **Event emission service** in `common/services/` — creates outbox entries within the same database transaction as the state change
3. **Delivery worker** — a Celery task that polls pending events, delivers them (via configurable handlers), and tracks delivery status with retry-with-backoff
4. **Admin interface** — for monitoring and manual retry of failed events

### OutboxEvent Model

<!-- Amendment 2026-02-26: Fixed uuid7 import to use common.utils wrapper per conventions (discussions.md Q1), clarified Status choices (Q5) -->
```python
class OutboxEvent(TimeStampedModel):
    id = UUIDField(primary_key=True, default=uuid7)  # from common.utils
    aggregate_type = CharField(max_length=100)    # e.g., "UploadFile", "User"
    aggregate_id = CharField(max_length=100)       # str(pk) of the source record
    event_type = CharField(max_length=100)         # e.g., "file.stored", "user.created"
    payload = JSONField(default=dict)              # full serialized event data
    status = CharField(...)                        # pending → delivered / failed / expired
    idempotency_key = CharField(max_length=255)    # deduplication
    attempts = PositiveIntegerField(default=0)
    max_attempts = PositiveIntegerField(default=5)
    next_attempt_at = DateTimeField(null=True)
    delivered_at = DateTimeField(null=True)
    error_message = TextField(blank=True)
```

**Key design decisions** (from PEP 0003 discussions.md Q9):
- **Name**: `OutboxEvent` — consistent noun-phrase model naming
- **Location**: `common/` app — cross-cutting, reusable by any app
- **No FK**: Uses `aggregate_type` + `aggregate_id` instead of FK to specific models. Events are self-contained — consumers read the payload, not the source table
- **Constraint**: `UniqueConstraint(fields=["event_type", "idempotency_key"])` — prevents duplicate events

### Event Delivery

The delivery worker is a Celery periodic task that:
1. Queries `OutboxEvent` records with `status=pending` and `next_attempt_at <= now()`
2. Processes events through configurable handler functions (registered per `event_type`)
3. On success: sets `status=delivered`, records `delivered_at`
4. On failure: increments `attempts`, sets `next_attempt_at` with exponential backoff, sets `status=failed` if `attempts >= max_attempts`

## Rationale

The transactional outbox pattern is well-established (Debezium, Axon, django-outbox-pattern). Writing events to the outbox table in the same database transaction as the state change guarantees that events are created if and only if the state change succeeds. A separate delivery process ensures events eventually reach consumers, with retry semantics for transient failures.

Placing the outbox in `common/` makes it available to all apps. The aggregate/payload pattern decouples the outbox from any specific domain model, allowing `accounts`, `uploads`, and future apps to emit events without schema changes.

## Out of Scope

- **Specific event handlers** — This PEP delivers the infrastructure (model, emission service, delivery worker). Actual event handlers for specific event types (e.g., "send email on `user.created`") are implemented by consumer PEPs.
- **Event schema registry** — No formal schema validation for event payloads. Application-level validation in handlers if needed.
- **Change Data Capture (CDC)** — The delivery mechanism is polling-based, not CDC. CDC (e.g., Debezium + PostgreSQL logical replication) is a future optimization.
- **Dead letter queue** — Failed events remain in the outbox table with `status=failed`. A separate archival/DLQ mechanism is deferred.

## Acceptance Criteria

- [ ] `OutboxEvent` model exists in `common/models.py` with UUID v7 PK, aggregate/payload fields, status lifecycle, retry tracking
- [ ] `UniqueConstraint(fields=["event_type", "idempotency_key"])` prevents duplicate events
- [ ] `emit_event(aggregate_type, aggregate_id, event_type, payload)` service creates outbox entries
- [ ] Delivery Celery task polls and processes pending events with retry-with-backoff
- [ ] Admin class registered for `OutboxEvent` with monitoring fields
- [ ] All tests pass (model, service, task)
- [ ] `python manage.py check` passes
- [ ] `aikb/` documentation updated

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-25 | — | Proposed | Initial creation (deferred from PEP 0003 discussions.md Q9) |
