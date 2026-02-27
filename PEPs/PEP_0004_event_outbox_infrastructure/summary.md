# PEP 0004: Event Outbox Infrastructure

| Field | Value |
|-------|-------|
| **PEP** | 0004 |
| **Title** | Event Outbox Infrastructure |
| **Author** | Doorito Team |
| **Status** | Implementing |
| **Risk** | Medium |
| **Created** | 2026-02-25 |
| **Updated** | 2026-02-26 |
| **Related PEPs** | PEP 0003 (Extend Data Models — outbox deferred from there) |
| **Depends On** | PEP 0003 |

---

## Problem Statement

Doorito needs a reliable mechanism for delivering domain events (e.g., `file.stored`, `user.created`) to downstream consumers. Without this, event-driven workflows require ad-hoc solutions that risk event loss, duplication, or tight coupling between producers and consumers.

PEP 0003 originally included a `PortalEventOutbox` model in the `uploads` app, but the Design Review identified several problems: the "Portal" prefix was meaningless, placing it in `uploads/` limited reuse, a hard FK to `IngestFile` coupled it to uploads, and defining the schema without a delivery worker meant rows would accumulate forever. The outbox was deferred to this dedicated PEP for a complete design.

## Proposed Solution

Implement a generic transactional outbox in the `common` app. The outbox provides reliable, at-least-once event delivery using the transactional outbox pattern:

1. **`OutboxEvent` model** in `common/models.py` — a self-contained event record using the aggregate/payload pattern (no FK to specific models)
<!-- Amendment 2026-02-26: Clarified emit_event dispatch (Q15), softened handler language pending Open Thread resolution -->
2. **Event emission service** in `common/services/` — creates outbox entries within the same database transaction as the state change, dispatches delivery via `transaction.on_commit()` (wrapped in error handling for eager mode safety — see discussions.md Q15)
3. **Delivery worker** — a Celery task that polls pending events, processes them (handler mechanism deferred to consumer PEPs — see discussions.md Q18), and tracks delivery status with retry-with-backoff
4. **Admin interface** — for monitoring and manual retry of failed events

### OutboxEvent Model

<!-- Amendment 2026-02-26: Fixed uuid7 import to use common.utils wrapper per conventions (discussions.md Q1), clarified Status choices (Q5) -->
<!-- Amendment 2026-02-26: Added DjangoJSONEncoder (Q9), partial index (Q10), next_attempt_at default (Q11), status max_length -->
<!-- Amendment 2026-02-26: Simplified to 3-state lifecycle per Q16 — PENDING, DELIVERED, FAILED (dropped EXPIRED) -->
<!-- Amendment 2026-02-26: Fixed choices=Status to choices=Status.choices per codebase convention (Q22) -->
```python
class OutboxEvent(TimeStampedModel):
    id = UUIDField(primary_key=True, default=uuid7)  # from common.utils
    aggregate_type = CharField(max_length=100)    # e.g., "UploadFile", "User"
    aggregate_id = CharField(max_length=100)       # str(pk) of the source record
    event_type = CharField(max_length=100)         # e.g., "file.stored", "user.created"
    payload = JSONField(default=dict, encoder=DjangoJSONEncoder)  # handles UUID, datetime, Decimal
    status = CharField(max_length=20, choices=Status.choices, default=Status.PENDING)  # pending → delivered / failed
    idempotency_key = CharField(max_length=255)    # deduplication
    attempts = PositiveIntegerField(default=0)
    max_attempts = PositiveIntegerField(default=5)
    next_attempt_at = DateTimeField(null=True)     # set to now() on creation; null when terminal
    delivered_at = DateTimeField(null=True)
    error_message = TextField(blank=True)

    class Meta:
        indexes = [
            Index(fields=["next_attempt_at"], condition=Q(status="pending"),
                  name="idx_outbox_event_pending_next_attempt"),
        ]
        constraints = [
            UniqueConstraint(fields=["event_type", "idempotency_key"],
                             name="unique_event_type_idempotency_key"),
        ]
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
3. On success: sets `status=delivered`, records `delivered_at`, sets `next_attempt_at=None`
4. On failure: increments `attempts`, sets `next_attempt_at` with exponential backoff (status stays `pending`); sets `status=failed` and `next_attempt_at=None` only when `attempts >= max_attempts` (terminal)

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
- [ ] `emit_event(aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None)` service creates outbox entries (auto-generates key when None — see discussions.md Q12)
- [ ] Delivery Celery task polls and processes pending events with retry-with-backoff
- [ ] Admin class registered for `OutboxEvent` with monitoring fields
- [ ] All tests pass (model, service, task)
- [ ] `python manage.py check` passes
- [ ] `aikb/` documentation updated

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-25 | — | Proposed | Initial creation (deferred from PEP 0003 discussions.md Q9) |
