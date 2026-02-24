# Signals & Event-Driven Patterns

**No signal handlers are defined yet** in the Doorito skeleton. This file documents the conventions for when they are added.

## Convention

Signals serve three primary purposes:
1. **Cache invalidation** -- clearing caches when underlying data changes
2. **Side effects** -- triggering notifications, creating related objects
3. **Staleness marking** -- flagging cached data for recomputation

## File Organization

Each app owns its own signals in `{app}/signals.py`:

```python
# {app}/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender="catalog.Product")
def on_product_save(sender, instance, **kwargs):
    # Use lazy imports to avoid circular dependencies
    from some.service import invalidate_cache
    invalidate_cache(instance.id)
```

## Registration

Signal handlers must be registered in the app's `ready()` method:

```python
# {app}/apps.py
class MyAppConfig(AppConfig):
    name = "myapp"

    def ready(self):
        import myapp.signals  # noqa: F401
```

## Important Notes

- Use lazy imports in signal handlers to avoid circular dependency issues
- Use `safe_dispatch()` from `common/utils.py` for signals that should never break the primary operation
- Signal registration happens in `{app}/apps.py` `ready()` method via `import {app}.signals`
