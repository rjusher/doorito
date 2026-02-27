# PEP 0007: File Portal Pipeline

| Field | Value |
|-------|-------|
| **PEP** | 0007 |
| **Title** | File Portal Pipeline |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | High |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Related PEPs** | PEP 0004 (Event Outbox Infrastructure), PEP 0006 (S3 Upload Storage) |
| **Depends On** | PEP 0006 |
| **Enables** | — |

---

## Problem Statement

Doorito is intended to function as a **file portal**: a system where users upload files to an S3 bucket, the system emits a webhook to notify an external AI agent that operates on those files via a shared S3 connection, and the system garbage-collects files after a configurable TTL.

The building blocks exist individually but are not wired into a functional pipeline:

- **Upload infrastructure exists but has no entry point.** The upload models (`UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart`) and services (`create_upload_file`, `validate_file`, etc.) are implemented, but no views or API endpoints call them. Users cannot upload files.
- **Outbox events are created but never delivered.** PEP 0006 adds `file.stored` event emission via the outbox, and PEP 0004 implemented the `OutboxEvent` model with a delivery task. However, `process_pending_events()` marks events as DELIVERED without actually posting to any external system — there is no HTTP webhook delivery handler and no way to configure a destination URL.
- **TTL cleanup runs silently.** The `cleanup_expired_upload_files_task` deletes files after `FILE_UPLOAD_TTL_HOURS`, but the external consumer (the AI agent sharing the S3 bucket) receives no notification that a file is about to be or has been removed. If the agent hasn't finished processing, data is lost without warning.

Without this PEP, Doorito has storage, an event table, and a cleanup cron — but no usable file portal.

## Proposed Solution

Implement the end-to-end file portal pipeline by adding four components that connect the existing infrastructure into a working system:

### 1. Upload Page and View

Add an upload page to the `frontend` app at `/app/upload/` where authenticated users can select and upload files via a drag-and-drop interface. The view handles `multipart/form-data` POST requests, delegates to the existing `create_upload_file` service, and returns upload results. HTMX provides progress feedback without full-page reloads.

### 2. WebhookEndpoint Model

Add a `WebhookEndpoint` model to the `common` app that stores configured webhook destinations:

- `url` — the target URL to POST events to
- `secret` — a shared secret for HMAC-SHA256 request signing (so consumers can verify authenticity)
- `event_types` — a JSON list of event types to subscribe to (e.g., `["file.stored", "file.expiring"]`), or empty `[]` for all events. Exact match only — no wildcard patterns.
- `is_active` — boolean toggle to enable/disable delivery
- Standard `TimeStampedModel` fields

Admin interface for managing endpoints. Multiple endpoints can be configured (fan-out delivery).

### 3. Webhook HTTP Delivery Handler

Replace the placeholder logic in `process_pending_events()` with actual HTTP POST delivery:

- For each pending `OutboxEvent`, find all active `WebhookEndpoint` records whose `event_types` match the event's `event_type`
- POST the event payload as JSON to each matching endpoint URL
- Include an `X-Webhook-Signature` header with an HMAC-SHA256 signature of the request body, keyed by the endpoint's `secret`
- Include an `X-Webhook-Event` header with the event type and an `X-Webhook-Delivery` header with the event ID for consumer-side deduplication
- On HTTP 2xx: mark the event as DELIVERED (only when ALL matching endpoints succeed)
- On HTTP 4xx/5xx or network error: increment attempts, set `next_attempt_at` with exponential backoff, re-deliver to ALL matching endpoints on retry (consumers must be idempotent — use `X-Webhook-Delivery` header for deduplication)
- On `attempts >= max_attempts`: transition to FAILED status
- Use `httpx` synchronous client with a short timeout (10s connect, 30s read) and connection pooling within each batch to avoid blocking the worker on slow consumers
- HTTP calls happen OUTSIDE `select_for_update` transactions to avoid holding row locks during network I/O

### 4. Pre-Expiry Notification Event

Before the cleanup task deletes a file, emit a `file.expiring` outbox event with the file's metadata and S3 URL. This gives the external consumer a chance to finish processing or copy the file before it's removed. The event is emitted a configurable period before the actual TTL expiry (e.g., 1 hour before deletion) via a separate sweep task, or at deletion time with a grace period.

### From the user's perspective

1. User logs in and navigates to `/app/upload/`
2. User drags files onto the upload zone (or clicks to browse)
3. Files are uploaded to S3 via the Django view (server-side)
4. The external AI agent system receives an HTTP webhook with the file's S3 URL, content type, and metadata
5. The AI agent accesses the file directly from the shared S3 bucket
6. Before the file's TTL expires, the AI agent receives a `file.expiring` webhook
7. After the TTL, the cleanup task removes the file from S3

## Rationale

- **Upload via Django views (not direct-to-S3):** Server-side uploads through Django views keep the upload flow simple, allow server-side validation (file size, type), and work with the existing `create_upload_file` service. Direct browser-to-S3 uploads via presigned URLs are a future optimization for large files but add complexity (presigned URL generation endpoint, multipart upload coordination, completion callback).
- **WebhookEndpoint model (not settings-based config):** A database model allows runtime configuration via the admin UI, supports multiple endpoints (fan-out), per-endpoint enable/disable, and per-endpoint secrets. Settings-based config would require redeployment for changes and doesn't scale to multiple consumers.
- **HMAC-SHA256 signing (not bearer tokens):** HMAC signing lets consumers verify that the webhook payload was sent by Doorito and hasn't been tampered with, without requiring the consumer to store API credentials. It's the industry standard for webhook security (used by GitHub, Stripe, Shopify).
- **httpx (not requests):** `httpx` supports both sync and async modes, has a cleaner timeout API, and is well-maintained. It adds minimal dependency weight. `requests` would also work but `httpx` is the modern choice.
- **Pre-expiry notification:** Since the S3 bucket is shared and the consumer has direct S3 access, deleting files without warning could interrupt in-progress AI processing. The `file.expiring` event gives consumers time to react.

## Alternatives Considered

### Alternative 1: External webhook relay service (e.g., Svix, Hookdeck)

- **Description**: Use a managed webhook delivery service instead of building in-app delivery. Doorito would POST events to the relay service, which handles delivery, retries, and monitoring.
- **Pros**: Battle-tested delivery infrastructure. Built-in monitoring dashboard, replay, rate limiting. Offloads retry logic from the app.
- **Cons**: Adds an external service dependency and cost. Requires another set of credentials and configuration. Adds latency (app → relay → consumer). Overkill for a single-consumer file portal.
- **Why rejected**: Doorito's use case is a single external AI agent consumer with low event volume. The outbox infrastructure already handles retry and persistence. A managed relay service adds unnecessary complexity and cost at this stage. Can be reconsidered if delivery requirements grow.

### Alternative 2: Direct S3 event notifications (S3 → SNS/SQS → consumer)

- **Description**: Configure S3 bucket event notifications to notify the consumer directly when objects are created/deleted, bypassing Doorito's outbox entirely.
- **Pros**: No application code for notification delivery. S3-native, highly reliable. Works even if Doorito is down.
- **Cons**: Ties the architecture to AWS S3 (not S3-compatible providers — MinIO has limited event support). The consumer loses Doorito-enriched metadata (user, batch, content type validation results) since S3 events only contain the object key and basic metadata. Requires AWS infrastructure configuration outside the application. Doesn't support the `file.expiring` pre-notification pattern.
- **Why rejected**: Vendor lock-in, loss of application-level metadata in events, and inability to support the pre-expiry notification pattern. The outbox approach keeps the pipeline under application control and works with any S3-compatible provider.

### Alternative 3: Upload API via Django REST Framework

- **Description**: Add DRF as a dependency and implement upload endpoints as DRF views with serializers, authentication classes, and throttling.
- **Pros**: Standardized API patterns. Built-in serialization, validation, pagination, and throttling. OpenAPI schema generation.
- **Cons**: Adds a heavy dependency (DRF + its transitive deps) for what is essentially a single file upload endpoint. The portal is for authenticated web users, not programmatic API consumers. DRF's serializer/viewset patterns are overkill for multipart file upload.
- **Why rejected**: The upload interface is a web UI for human users, not a REST API for machines. A plain Django view with `@frontend_login_required` and HTMX is simpler, consistent with the existing frontend app patterns, and avoids a new dependency. A proper REST API can be added later if programmatic upload access is needed.

## Impact Assessment

### Affected Components

- **Models**: `common/models.py` — add `WebhookEndpoint` model
- **Services**: `common/services/outbox.py` — replace placeholder delivery logic with HTTP POST handler; `common/services/webhook.py` (new) — webhook delivery, signing, endpoint matching
- **Views**: `frontend/views/upload.py` (new) — upload page view and file upload handler
- **Templates**: `frontend/templates/frontend/upload/` (new) — upload page with drag-and-drop UI
- **URLs**: `frontend/urls.py` — add `/app/upload/` route
- **Admin**: `common/admin.py` — add `WebhookEndpointAdmin`
- **Tasks**: `uploads/tasks.py` — add pre-expiry notification to cleanup task
- **Dependencies**: `requirements.in` — add `httpx`
- **Settings**: `boot/settings.py` — add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting

### Migration Impact

- **Database migrations required?** Yes. One new model (`WebhookEndpoint`) in the `common` app.
- **Data migration needed?** No.
- **Backward compatibility**: Non-breaking. New features only. Existing outbox events will begin to be delivered via HTTP once a `WebhookEndpoint` is configured. Without any configured endpoints, behavior is unchanged (events marked as delivered with no HTTP calls).

### Performance Impact

- **Webhook delivery**: Each outbox event triggers HTTP POST(s) to configured endpoints. With `httpx` timeouts and the existing batch processing (100 events per run), this is bounded. Slow consumers are handled by the retry/backoff mechanism, not by blocking the worker.
- **Upload handling**: File uploads go through Django (server-side) to S3. Upload size is bounded by `FILE_UPLOAD_MAX_SIZE` (50 MB default). Large file handling is deferred to a future presigned URL PEP.
- **Task queue**: One additional periodic task (pre-expiry sweep) and increased work for the delivery task (HTTP calls instead of no-op). Both run on the `default` queue.

## Out of Scope

- **Direct browser-to-S3 uploads via presigned URLs** — Deferred to a future PEP. This PEP routes uploads through Django for simplicity.
- **REST API for programmatic uploads** — The upload interface is a web UI. API access can be added later.
- **Webhook delivery monitoring dashboard** — Admin list view is sufficient for now. A dedicated monitoring UI is a future enhancement.
- **Webhook endpoint management UI in the frontend** — Endpoints are managed via Django admin only.
- **Event filtering beyond event_type matching** — No payload-based filtering or content routing. Endpoints receive all matching events.
- **Webhook delivery rate limiting** — Not needed for low-volume single-consumer use case. Can be added if consumer capacity becomes a concern.
- **Chunked/resumable upload UI** — The upload models support chunking (UploadSession/UploadPart) but the UI uses simple single-request uploads for now.

## Acceptance Criteria

- [ ] `/app/upload/` page is accessible to authenticated users and renders a drag-and-drop file upload interface
- [ ] Files uploaded via the upload page are stored using the configured storage backend (S3 in production, local in dev)
- [ ] Upload validation enforces `FILE_UPLOAD_MAX_SIZE` and `FILE_UPLOAD_ALLOWED_TYPES` settings
- [ ] `WebhookEndpoint` model exists in `common/models.py` with `url`, `secret`, `event_types`, and `is_active` fields
- [ ] `WebhookEndpointAdmin` is registered in Django admin with list display and filtering
- [ ] `process_pending_events()` delivers events via HTTP POST to all matching active `WebhookEndpoint` records
- [ ] Webhook requests include `X-Webhook-Signature` (HMAC-SHA256), `X-Webhook-Event`, and `X-Webhook-Delivery` headers
- [ ] Webhook delivery respects the existing retry/backoff logic (increment attempts, exponential `next_attempt_at`)
- [ ] Events with no matching active endpoints are marked as DELIVERED (no-op delivery, not an error)
- [ ] `httpx` is listed in `requirements.in` and compiled into `requirements.txt`
- [ ] A `file.expiring` outbox event is emitted before TTL-based file cleanup, containing the file's metadata and URL
- [ ] `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting controls how far before expiry the notification fires (default: 1 hour)
- [ ] Sidebar navigation includes an "Upload" link to `/app/upload/`
- [ ] `python manage.py check` passes
- [ ] All tests pass (upload view, webhook delivery, pre-expiry notification)
- [ ] `aikb/` documentation is updated to reflect new components

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
<!-- Amendment 2026-02-27: Updated based on discussions — clarified per-event delivery tracking, exact-match event types, sync httpx client, transaction boundary strategy, delivery batch size rationale -->
