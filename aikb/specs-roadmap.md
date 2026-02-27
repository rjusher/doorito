# Feature Specs & Roadmap

## Current State

The project is a **clean skeleton** -- no feature specifications exist and no roadmap items have been defined. The foundation is in place with Django 6.0, PostgreSQL, Celery, and a minimal frontend.

## Development Process

All future feature development should use the **PEP (Project Enhancement Proposal)** workflow:

1. `make claude-pep-draft DESC="description"` -- Create a new PEP
2. `make claude-pep-research PEP=NNNN` -- Research the codebase
3. `make claude-pep-plan PEP=NNNN` -- Refine the implementation plan
4. `make claude-pep-implement PEP=NNNN` -- Execute the plan
5. `make claude-pep-finalize PEP=NNNN` -- Update aikb, LATEST.md, cleanup

See `PEPs/ABOUT.md` for full PEP documentation and `CLAUDE.md` for the PEP lifecycle.

## What's Ready

| Component | Status |
|-----------|--------|
| Django project structure (boot/) | Ready |
| Custom User model (accounts) | Ready |
| TimeStampedModel + MoneyField (common) | Ready |
| Frontend auth (login/register/logout) | Ready |
| Frontend dashboard (placeholder) | Ready |
| Template hierarchy (base + auth + minimal) | Ready |
| Tailwind CSS v4 standalone CLI | Ready |
| HTMX + Alpine.js vendored | Ready |
| Celery with Postgres broker | Ready |
| Docker Compose (web + db + worker + beat) | Ready |
| CLI skeleton (doorito script) | Ready |
| PEP workflow system | Ready |
| aikb documentation system | Ready |
| File upload infrastructure (uploads) | Ready |
| Event outbox infrastructure (common) | Ready |

## What's Not Built Yet

Some natural next steps (each should be a PEP):

- Upload frontend views (forms, templates, URL routes for file upload UI)
- Workflow management (workflow models, dispatch, AI task orchestration)
- REST API
- Multi-tenancy / RBAC
- S3 / cloud storage for media files
- Production deployment (K8s, etc.)
