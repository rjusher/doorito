# PEP 0010: Authentication and API Access — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0010 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | M |

---

## Context Files

- `aikb/architecture.md` — App structure, URL patterns
- `aikb/models.md` — User model details
- `accounts/models.py` — Custom User model
- `frontend/decorators.py` — Existing `@frontend_login_required` decorator
- `boot/settings.py` — Auth configuration

## Prerequisites

- PEP 0008 (Canonical Domain Model) must be implemented

## Implementation Steps

- [ ] **Step 1**: Create API token model
  - Files: Portal app or accounts `models.py`
  - Details: Token model with FK to User, token value (hashed), created_at, is_active
  - Verify: `python manage.py makemigrations --check`

- [ ] **Step 2**: Create authentication utility
  - Files: Portal app `auth.py`
  - Details: Function to extract and validate auth from request (session or Bearer token)
  - Verify: Unit tests pass

- [ ] **Step 3**: Create API auth decorator/mixin
  - Files: Portal app `decorators.py`
  - Details: `@api_auth_required` decorator that checks session or token auth
  - Verify: Unit tests pass

- [ ] **Step 4**: Add token admin
  - Files: Portal app or accounts `admin.py`
  - Details: Admin class for managing API tokens
  - Verify: `python manage.py check`

- [ ] **Step 5**: Add token management command (optional)
  - Files: Portal app `management/commands/create_api_token.py`
  - Details: `manage.py create_api_token <username>` command
  - Verify: `python manage.py create_api_token --help`

## Testing

- [ ] Unit tests for token validation
- [ ] Unit tests for decorator (authenticated vs unauthenticated)
- [ ] Test that uploaded_by is populated correctly

## Rollback Plan

- Reverse token migration
- Remove auth decorator from endpoints

## aikb Impact Map

- [ ] `aikb/models.md` — Add API token model documentation
- [ ] `aikb/services.md` — Add auth utility documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — Add token admin
- [ ] `aikb/cli.md` — Add token management command
- [ ] `aikb/architecture.md` — Document auth strategy
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Document API authentication

## Final Verification

### Acceptance Criteria

- [ ] **Unauthenticated rejection**: Request without session or token gets 401
  - Verify: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/uploads/sessions`
- [ ] **Session auth works**: Logged-in user can access endpoints
  - Verify: Manual test via browser
- [ ] **Token auth works**: Bearer token grants access
  - Verify: `curl -H "Authorization: Bearer <token>" http://localhost:8000/uploads/sessions`

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0010_authentication_api_access/`
