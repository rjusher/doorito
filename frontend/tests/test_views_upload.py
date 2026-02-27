"""Tests for the upload view."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from uploads.models import UploadBatch, UploadFile

# Override staticfiles storage to avoid WhiteNoise manifest issues in tests
_SIMPLE_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}


@pytest.fixture(autouse=True)
def _simple_storages(settings):
    """Override STORAGES to avoid WhiteNoise manifest issues."""
    settings.STORAGES = _SIMPLE_STORAGES


@pytest.mark.django_db
class TestUploadViewGet:
    """Tests for GET /app/upload/."""

    def test_authenticated_user_gets_200(self, user):
        client = Client()
        client.force_login(user)
        response = client.get("/app/upload/")
        assert response.status_code == 200

    def test_unauthenticated_redirects_to_login(self):
        client = Client()
        response = client.get("/app/upload/")
        assert response.status_code == 302
        assert "/app/login/" in response.url


@pytest.mark.django_db
class TestUploadViewPost:
    """Tests for POST /app/upload/."""

    def test_post_with_files_creates_records(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        client = Client()
        client.force_login(user)

        file1 = SimpleUploadedFile("doc1.pdf", b"content1")
        file2 = SimpleUploadedFile("doc2.pdf", b"content2")
        response = client.post(
            "/app/upload/", {"files": [file1, file2]}, follow=False
        )

        assert response.status_code == 302
        assert UploadFile.objects.count() == 2
        assert UploadBatch.objects.count() == 1

    def test_post_with_no_files_returns_error(self, user):
        client = Client()
        client.force_login(user)
        response = client.post("/app/upload/", {}, follow=True)

        assert response.status_code == 200
        messages_list = list(response.context["messages"])
        assert len(messages_list) == 1
        assert "No files selected" in str(messages_list[0])

    def test_post_with_too_many_files_returns_error(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        client = Client()
        client.force_login(user)

        files = [
            SimpleUploadedFile(f"doc{i}.pdf", b"content") for i in range(11)
        ]
        response = client.post(
            "/app/upload/", {"files": files}, follow=True
        )

        assert response.status_code == 200
        messages_list = list(response.context["messages"])
        assert len(messages_list) == 1
        assert "Too many files" in str(messages_list[0])
        assert UploadFile.objects.count() == 0

    def test_non_htmx_post_redirects(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        client = Client()
        client.force_login(user)

        file = SimpleUploadedFile("doc.pdf", b"content")
        response = client.post("/app/upload/", {"files": [file]}, follow=False)

        assert response.status_code == 302
        assert response.url == "/app/upload/"


@pytest.mark.django_db
class TestUploadViewHtmx:
    """Tests for HTMX POST /app/upload/."""

    def test_htmx_post_returns_partial(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        client = Client()
        client.force_login(user)

        file = SimpleUploadedFile("doc.pdf", b"content")
        response = client.post(
            "/app/upload/",
            {"files": [file]},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        # HTMX response should not redirect
        assert "Upload Results" in response.content.decode()

    def test_htmx_post_no_files_returns_error_partial(self, user):
        client = Client()
        client.force_login(user)
        response = client.post(
            "/app/upload/",
            {},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        assert "No files selected" in response.content.decode()
