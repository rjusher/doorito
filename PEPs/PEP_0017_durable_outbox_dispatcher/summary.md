# PEP 0017: Durable Outbox Dispatcher

| Field | Value |
|-------|-------|
| **PEP** | 0017 |
| **Title** | Durable Outbox Dispatcher |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | High |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0014, PEP 0016 |

---

## Problem Statement

The AI runner or network may be temporarily unavailable when file upload events need to be delivered. Without a durable dispatcher, events could be lost during outages, leading to files that are stored but never processed by the runner.

## Proposed Solution

Implement a dispatcher loop that reliably delivers outbox events to the runner endpoint with retry and backoff.

### Dispatcher Loop

1. **Select** outbox rows where:
   - `status` in (`PENDING`, `FAILED`)
   - `next_attempt_at <= now()`
2. **Lock rows** (SELECT FOR UPDATE SKIP LOCKED) to prevent concurrent workers from double-sending
3. **Mark SENDING** to indicate delivery in progress
4. **POST** event payload to the configured runner endpoint
5. **On success** → mark `DELIVERED`, record delivered_at timestamp
6. **On failure** → mark `FAILED`, increment attempt_count, set next_attempt_at with backoff

### Backoff Strategy

- Exponential backoff: `base_delay * 2^attempt_count`
- Cap at a configurable maximum delay (e.g., 1 hour)
- Optional jitter to prevent thundering herd

### Idempotency

- Unique constraint on `(event_type, idempotency_key)` prevents duplicate event creation
- Runner is expected to deduplicate by `event_id` (defensive against rare double-delivery)

### Execution

- Runs as a Celery periodic task (via celery-beat)
- Can also be triggered on-demand via `transaction.on_commit` after finalization (PEP 0014)

## Rationale

The outbox pattern ensures at-least-once delivery even when the runner or network is temporarily unavailable. Row-level locking with SKIP LOCKED enables safe concurrent execution by multiple workers. Exponential backoff prevents overwhelming a recovering runner. The combination of periodic sweeps and on-commit triggers balances latency (immediate delivery attempt) with reliability (periodic retry of failures).

## Alternatives Considered

### Alternative 1: Direct HTTP call during finalization (no outbox)

- **Description**: POST to the runner directly from the finalization service.
- **Pros**: Simpler, lower latency for the success case.
- **Cons**: If the runner is down, the event is lost. Retry logic complicates the finalization service. Transaction boundary issues (HTTP call inside DB transaction).
- **Why rejected**: Durability requires decoupling event creation from delivery.

### Alternative 2: Message queue (RabbitMQ, Kafka)

- **Description**: Publish events to a dedicated message broker.
- **Pros**: Battle-tested delivery guarantees. Built-in retry and dead-letter queues.
- **Cons**: Adds a new infrastructure dependency. Overkill for the current scale. The existing PostgreSQL-based Celery broker already provides adequate queuing.
- **Why rejected**: The outbox pattern with PostgreSQL provides sufficient guarantees without additional infrastructure.

## Impact Assessment

### Affected Components

- **Tasks**: New Celery periodic task for outbox dispatch sweep
- **Services**: New dispatcher service
- **Settings**: Runner endpoint URL, auth secret, backoff parameters
- **Models**: PortalEventOutbox status transitions

### Migration Impact

- **Database migrations required?** No (model from PEP 0008)
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking

### Performance Impact

- Periodic sweep queries with SKIP LOCKED are efficient
- HTTP POST to runner is async (within Celery task)
- Backoff prevents excessive retries

## Out of Scope

- Runner-side event processing implementation
- Dead-letter queue or permanent failure handling
- Event replay / redelivery UI (covered partially in PEP 0018)
- Multi-endpoint fan-out (single runner endpoint)

## Acceptance Criteria

- [ ] Runner downtime does not lose events (events remain in outbox and are retried)
- [ ] Concurrent dispatcher workers do not double-send the same event (SKIP LOCKED)
- [ ] Failed events are retried with exponential backoff
- [ ] Backoff delay is capped at configurable maximum
- [ ] Successfully delivered events are marked DELIVERED with timestamp
- [ ] Periodic sweep task runs on configured interval via celery-beat
- [ ] Runner endpoint URL and auth secret are configurable via settings

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
