# Code Conventions & Patterns

This document describes the established patterns and conventions in the Doorito codebase. Follow these when adding new features or modifying existing code.

## Project Conventions

### Django App Organization
- **One `models.py` per app** (not a `models/` package)
- **Services in `{app}/services/`** -- business logic lives here, not in models or views
- **Signals in `{app}/signals.py`** -- registered in `apps.py` `ready()` method
- **Tasks in `{app}/tasks.py`** or `{app}/tasks/{module}.py` -- Celery task modules
- **Admin in `{app}/admin.py`** -- admin classes per app

### Model Patterns

**Base class**: Most models should inherit from `TimeStampedModel` (common app):
```python
from common.models import TimeStampedModel

class MyModel(TimeStampedModel):
    name = models.CharField(max_length=200)
    # ... fields
```

**Money fields**: Use `MoneyField` from common for all monetary amounts:
```python
from common.fields import MoneyField

price = MoneyField(verbose_name="price")  # DecimalField(max_digits=12, decimal_places=2)
```

**Reference fields**: Unique identifiers use `generate_reference()` from `common/utils.py`:
```python
from common.utils import generate_reference

reference = models.CharField(max_length=20, unique=True, default=partial(generate_reference, "ORD"))
```

**Status fields**: Use CharField with TextChoices, not IntegerChoices:
```python
class Status(models.TextChoices):
    PENDING = "pending", "Pending"
    ACTIVE = "active", "Active"

status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
```

### Service Layer Patterns

**Service functions** are the primary entry point for business logic:
```python
# {app}/services/{domain}.py
def create_widget(name, price):
    """Create a new widget with validation."""
    # Business logic here
    return widget
```

**Service delegation**: Views, admin, CLI, and tasks all delegate to services.

### Celery Task Patterns

```python
@shared_task(
    name="app.tasks.module.task_name",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def my_task(self, object_id):
    # Lazy imports to avoid circular dependencies
    from app.models import MyModel
    from app.services.my_service import do_thing

    obj = MyModel.objects.get(id=object_id)
    result = do_thing(obj)
    return {"status": "ok", "result": result}
```

### Signal Patterns

```python
# {app}/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender="myapp.MyModel")
def on_mymodel_save(sender, instance, **kwargs):
    from some.service import invalidate_cache
    invalidate_cache(instance.id)
```

- Use lazy imports in signal handlers
- Register signals in `apps.py` `ready()` method
- Use `safe_dispatch()` for signals that should never break the primary operation

### CLI Command Patterns

```python
@cli.command()
@click.argument("name")
def my_command(name):
    """Command description."""
    from app.services.something import do_thing
    result = do_thing(name)
    click.echo(f"Done: {result}")
```

### Docstring Conventions

**Module-level**: Every Python module should have a docstring explaining its purpose.

**Class-level**: All model classes should have docstrings explaining purpose and design decisions.

**Method-level**: Use the Args/Returns/Raises pattern for methods with parameters or side effects.

**Inline comments**: Only add "why" comments where the rationale isn't obvious.

### Import Conventions

```python
# Standard library
import logging
from datetime import timedelta

# Django
from django.conf import settings
from django.db import models
from django.utils import timezone

# Third-party
from celery import shared_task

# Local app
from common.models import TimeStampedModel
from common.fields import MoneyField
```

Enforced by Ruff isort rules.

### Frontend Patterns

**Template hierarchy** (3 base templates):
- `templates/base.html` -- Root base template loading Tailwind CSS, HTMX, Alpine.js with block slots: `title`, `content`, `extra_css`, `extra_js`
- `frontend/base.html` -- App shell for authenticated pages
- `frontend/base_auth.html` -- Centered card layout for auth pages (login, register)
- `frontend/base_minimal.html` -- Centered message for error pages (403, 404, 500)

**Template inheritance**: Page templates extend the appropriate base:
```html
{% extends "frontend/base_auth.html" %}
{% block title %}Login{% endblock %}
{% block content %}...{% endblock %}
```

**Tailwind CSS**: Use utility classes directly in templates. Design tokens are defined in `static/css/input.css` via `@theme {}`. After modifying templates, rebuild CSS with `make css` (or use `make css-watch` during development).

**HTMX**: Use `hx-get`, `hx-post`, `hx-target`, `hx-swap` attributes for server-driven partial updates. CSRF is auto-configured via `hx-headers` on `<body>` in base.html. Check `request.htmx` in views (provided by `django-htmx` middleware).

**Alpine.js**: Use `x-data`, `x-show`, `x-on`, `x-bind` for client-only interactivity (modals, toggles, dropdowns). Alpine.js is loaded with `defer`.

**Tool boundaries**:
- **Tailwind** = styling (colors, spacing, typography, layout, responsive)
- **HTMX** = server communication (fetch HTML fragments, form submissions, lazy loading)
- **Alpine.js** = client-only state (show/hide, counters, form validation UI, modals)

**Frontend view patterns**:
- Function-based views with `@frontend_login_required` decorator (redirects to `/app/login/` with `?next=` parameter)
- Template naming: `frontend/<module>/<page>.html` for full pages, `frontend/<module>/partials/<name>.html` for HTMX partials

## Code Quality Tools

### Ruff (Linting)
- Line length: 88 characters
- Python target: 3.12
- Configuration in `pyproject.toml`

### Black (Formatting)
- Line length: 88
- Python target: 3.12

### Pre-commit Hooks
Runs both Ruff and Black before each commit. Install with:
```bash
pre-commit install
```

## Naming Conventions

| Entity | Convention | Example |
|--------|-----------|---------|
| Models | PascalCase, singular | `ProductVariation`, `LiveSession` |
| Services | snake_case functions | `check_stock_level()`, `create_order()` |
| Tasks | snake_case with `_task` suffix | `expire_invitations_task` |
| CLI groups | kebab-case | `stock-alert`, `barcode-pool` |
| CLI commands | snake_case | `list`, `show`, `create` |
| Constants | UPPER_SNAKE_CASE | `CACHE_TTL` |
| Enums | PascalCase class, UPPER values | `Status.PENDING` |
| URL patterns | kebab-case | `/buy-intent/`, `/store-request/` |
