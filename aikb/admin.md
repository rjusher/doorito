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

## Future Conventions

When adding new admin classes:

- Use `list_select_related` to optimize database queries
- Use `list_filter` and `search_fields` for navigation
- Keep admin classes in their respective app's `admin.py` file
- For store-scoped models, consider a `StoreAdminMixin` to filter querysets
