# Service Layer Reference

Doorito uses a service layer pattern to encapsulate business logic outside of models and views. **No services have been implemented yet** -- this file documents the conventions for when they are added.

## Design Principles

1. **Models are data containers** -- they define fields, relationships, and simple computed properties.
2. **Services contain business logic** -- validation, multi-model coordination, side effects.
3. **Views/Admin call services** -- never perform complex logic directly.
4. **CLI commands delegate to services** -- all Click commands should call service functions.
5. **Tasks call services** -- Celery tasks should be thin wrappers around service calls.

## Convention

Services live in `{app}/services/` directories:

```
{app}/
└── services/
    ├── __init__.py
    └── {domain}.py    # One module per domain concern
```

Service functions are plain Python functions (not classes):

```python
# Example future service function
def create_widget(store, name, price, created_by=None):
    """Create a new widget with validation."""
    # Business logic here
    return widget
```

## Current State

No service directories or modules exist yet. When adding the first service to an app:

1. Create `{app}/services/__init__.py`
2. Create `{app}/services/{domain}.py` with the service functions
3. Import and call from views, admin, CLI, and tasks
