"""Unit tests for upload file cleanup task."""

from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from uploads.models import UploadFile
from uploads.tasks import cleanup_expired_upload_files_task


@pytest.fixture
def _media_root(tmp_path, settings):
    """Use a temporary directory for MEDIA_ROOT."""
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def make_upload(user, _media_root):
    """Factory fixture to create UploadFile instances."""

    def _make(hours_old=0, status=UploadFile.Status.STORED):
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
            status=status,
        )
        if hours_old > 0:
            old_time = timezone.now() - timedelta(hours=hours_old)
            UploadFile.objects.filter(pk=upload.pk).update(created_at=old_time)
            upload.refresh_from_db()
        return upload

    return _make


@pytest.mark.django_db
class TestCleanupExpiredUploadFilesTask:
    """Tests for cleanup_expired_upload_files_task."""

    def test_no_expired_uploads(self, user, _media_root):
        """No expired upload files returns deleted=0, remaining=0."""
        result = cleanup_expired_upload_files_task()
        assert result == {"deleted": 0, "remaining": 0}

    def test_expired_upload_deleted(self, make_upload, tmp_path):
        """Expired upload file with file on disk deletes both record and file."""
        upload = make_upload(hours_old=25)
        file_path = tmp_path / upload.file.name

        result = cleanup_expired_upload_files_task()

        assert result["deleted"] == 1
        assert result["remaining"] == 0
        assert not UploadFile.objects.filter(pk=upload.pk).exists()
        assert not file_path.exists()

    def test_expired_upload_missing_file(self, make_upload, tmp_path):
        """Expired upload file with missing file still deletes the record."""
        upload = make_upload(hours_old=25)
        file_path = tmp_path / upload.file.name
        if file_path.exists():
            file_path.unlink()

        result = cleanup_expired_upload_files_task()

        assert result["deleted"] == 1
        assert not UploadFile.objects.filter(pk=upload.pk).exists()

    def test_non_expired_upload_not_deleted(self, make_upload):
        """Non-expired upload file is not deleted."""
        upload = make_upload(hours_old=1)  # Only 1 hour old (TTL=24h)

        result = cleanup_expired_upload_files_task()

        assert result == {"deleted": 0, "remaining": 0}
        assert UploadFile.objects.filter(pk=upload.pk).exists()

    def test_batch_limit_honored(self, make_upload, settings):
        """Only BATCH_SIZE upload files are deleted per run."""
        from uploads import tasks

        original_batch_size = tasks.BATCH_SIZE
        tasks.BATCH_SIZE = 3

        try:
            for _ in range(5):
                make_upload(hours_old=25)

            result = cleanup_expired_upload_files_task()

            assert result["deleted"] == 3
            assert result["remaining"] == 2
            assert UploadFile.objects.count() == 2
        finally:
            tasks.BATCH_SIZE = original_batch_size
