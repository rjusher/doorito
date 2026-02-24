# Data Models Reference

Complete reference of all Django models in Doorito.

## Abstract Base Models (common)

### TimeStampedModel
Abstract model inherited by most models in the project. Defined in `common/models.py`.
- `created_at` -- DateTimeField (auto_now_add)
- `updated_at` -- DateTimeField (auto_now)

### MoneyField
Custom DecimalField (max_digits=12, decimal_places=2, default=0.00) for monetary amounts. Defined in `common/fields.py`. Includes a `MinValueValidator(0.00)` by default. Reports itself as a plain `DecimalField` in `deconstruct()` to avoid migration churn.

---

## Accounts App

### User (AbstractUser)
Custom user model extending Django's AbstractUser. No additional fields beyond what AbstractUser provides. `db_table = "user"`. Returns `email or username` from `__str__()`.

---

## Entity Relationship Summary

```
User (accounts.User, extends AbstractUser)
  └── standard Django auth fields (username, email, password, etc.)
```

That's it. The skeleton has only one concrete model. All future models should inherit from `TimeStampedModel` and use `MoneyField` for monetary amounts.
