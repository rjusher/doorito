# PEP 0010: Authentication and API Access

| Field | Value |
|-------|-------|
| **PEP** | 0010 |
| **Title** | Authentication and API Access |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008 |
| **Enables** | PEP 0011, PEP 0012, PEP 0013, PEP 0014, PEP 0015 |

---

## Problem Statement

Upload endpoints must not be anonymous. The ingest portal needs authentication for both the web UI (browser-based usage) and programmatic API access (CLI tools, scripts, CI/CD pipelines). Without authentication, any network-reachable client could upload files, exhaust storage, or abuse the system.

## Proposed Solution

Provide minimal but secure authentication covering two access patterns:

- **UI authentication** — Django session auth (already exists via the `frontend` app's login/register views)
- **API authentication** — Token-based auth for programmatic access

### Key Components

1. **API token model** — A simple token model tied to the User, suitable for bearer-token authentication
2. **Authentication middleware/decorator** — Check session auth or token auth on all upload-related endpoints
3. **`uploaded_by` field population** — When a file is created, the authenticated user is recorded on the `IngestFile.uploaded_by` field

### Endpoint Protection

All upload-related endpoints require authentication:
- `POST /uploads/sessions` (PEP 0011)
- `PUT /uploads/sessions/{id}/parts/{n}` (PEP 0012)
- `GET /uploads/sessions/{id}` (PEP 0013)
- `POST /uploads/sessions/{id}/finalize` (PEP 0014)
- `POST /batches` (PEP 0015)
- `GET /batches/{id}` (PEP 0015)

## Rationale

OSS should remain simple but secure. Session auth leverages Django's existing infrastructure. Token auth provides a lightweight mechanism for programmatic access without requiring OAuth complexity. This keeps the authentication surface minimal while covering all access patterns.

## Alternatives Considered

### Alternative 1: OAuth2 / OpenID Connect

- **Description**: Full OAuth2 flow with authorization server.
- **Pros**: Industry standard, supports third-party integrations.
- **Cons**: Significant complexity for an OSS ingest portal. Requires additional dependencies and infrastructure.
- **Why rejected**: Over-engineered for the use case. Can be added later if needed.

### Alternative 2: API keys only (no session auth)

- **Description**: All access via API keys, including browser UI.
- **Pros**: Single auth mechanism.
- **Cons**: Poor UX for browser users. Requires custom login flow.
- **Why rejected**: Session auth is already built into Django and the frontend app. No reason to replace it.

## Impact Assessment

### Affected Components

- **Models**: New API token model (portal app or accounts app)
- **Services**: Authentication checking service/utility
- **Views/Endpoints**: All upload endpoints decorated with auth requirement

### Migration Impact

- **Database migrations required?** Yes — new token table
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking

### Performance Impact

- Token lookup is a single indexed query — negligible overhead

## Out of Scope

- OAuth2 / OpenID Connect
- Role-based access control (RBAC)
- Rate limiting (deferred to PEP 0019)
- Token rotation / expiration policies
- Multi-tenancy / per-organization tokens

## Acceptance Criteria

- [ ] Unauthenticated requests to upload endpoints are rejected with 401
- [ ] Authenticated user (session) can create session and upload parts
- [ ] Authenticated user (token) can create session and upload parts
- [ ] `uploaded_by` field is populated on IngestFile when user is authenticated
- [ ] Token can be created and revoked via admin or management command

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
