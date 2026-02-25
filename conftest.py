"""Shared pytest fixtures for Doorito."""

import pytest


@pytest.fixture
def user(db):
    """Create a test user."""
    from accounts.models import User

    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
