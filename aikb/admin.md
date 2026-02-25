# Admin Interface Reference

The Django admin interface is minimal in the Doorito skeleton. It serves as a superuser/developer tool.

## Registered Admin Classes

### accounts/admin.py

```python
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass
```

The only registered admin class. Uses Django's built-in `UserAdmin` with no customizations.

## Access

- **URL**: `/admin/`
- **Auth**: Django's built-in superuser/staff authentication
- **Models visible**: User (via `accounts.UserAdmin`)

### uploads/admin.py

```python
@admin.register(IngestFile)
class IngestFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "user", "file_size", "mime_type", "status", "created_at")
    list_filter = ("status", "mime_type", "created_at")
    search_fields = ("original_filename", "user__email", "user__username")
    readonly_fields = ("file_size", "mime_type", "status", "error_message", "created_at", "updated_at")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
```

Uses `list_select_related = ("user",)` to prevent N+1 queries. `date_hierarchy` provides date-based navigation for upload history. Computed/auto fields are read-only to prevent manual override.

## Conventions

When adding new admin classes:

- Use `list_select_related` to optimize database queries
- Use `list_filter` and `search_fields` for navigation
- Keep admin classes in their respective app's `admin.py` file
