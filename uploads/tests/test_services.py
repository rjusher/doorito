"""Unit tests for upload file services."""

import hashlib
from datetime import timedelta

import pytest
from common.models import OutboxEvent
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from uploads.models import UploadBatch, UploadFile
from uploads.services.uploads import (
    compute_sha256,
    create_batch,
    create_upload_file,
    finalize_batch,
    mark_file_deleted,
    mark_file_failed,
    mark_file_processed,
    notify_expiring_files,
    validate_file,
)


class TestValidateFile:
    """Tests for validate_file service."""

    def test_valid_file(self):
        """Valid file within size limit returns (content_type, size_bytes)."""
        file = SimpleUploadedFile("report.pdf", b"fake pdf content")
        content_type, size_bytes = validate_file(file)
        assert content_type == "application/pdf"
        assert size_bytes == 16

    def test_file_exceeds_max_size(self):
        """File exceeding max_size raises ValidationError."""
        file = SimpleUploadedFile("big.pdf", b"x" * 100)
        with pytest.raises(ValidationError) as exc_info:
            validate_file(file, max_size=50)
        assert exc_info.value.code == "file_too_large"

    def test_unknown_extension_returns_octet_stream(self):
        """Unknown file extension returns application/octet-stream."""
        file = SimpleUploadedFile("data.xyz123", b"some data")
        content_type, size_bytes = validate_file(file)
        assert content_type == "application/octet-stream"
        assert size_bytes == 9

    @override_settings(FILE_UPLOAD_ALLOWED_TYPES=["application/pdf"])
    def test_disallowed_mime_type(self):
        """MIME type not in FILE_UPLOAD_ALLOWED_TYPES raises ValidationError."""
        file = SimpleUploadedFile("image.png", b"fake png")
        with pytest.raises(ValidationError) as exc_info:
            validate_file(file)
        assert exc_info.value.code == "file_type_not_allowed"

    @override_settings(FILE_UPLOAD_ALLOWED_TYPES=None)
    def test_allowed_types_none_accepts_all(self):
        """FILE_UPLOAD_ALLOWED_TYPES=None accepts any file type."""
        file = SimpleUploadedFile("image.png", b"fake png")
        content_type, _size_bytes = validate_file(file)
        assert content_type == "image/png"

    def test_custom_max_size_overrides_setting(self):
        """Custom max_size parameter overrides FILE_UPLOAD_MAX_SIZE."""
        file = SimpleUploadedFile("small.pdf", b"x" * 10)
        _content_type, size_bytes = validate_file(file, max_size=20)
        assert size_bytes == 10

        with pytest.raises(ValidationError) as exc_info:
            validate_file(file, max_size=5)
        assert exc_info.value.code == "file_too_large"


class TestComputeSha256:
    """Tests for compute_sha256 service."""

    def test_known_hash(self):
        """Known content produces expected SHA-256 hash."""
        content = b"hello world"
        file = SimpleUploadedFile("test.txt", content)
        expected = hashlib.sha256(content).hexdigest()
        assert compute_sha256(file) == expected


@pytest.mark.django_db
class TestCreateUploadFile:
    """Tests for create_upload_file service."""

    def test_valid_upload_creates_stored_record(self, user, tmp_path, settings):
        """Valid file creates UploadFile with status=STORED and sha256."""
        settings.MEDIA_ROOT = tmp_path
        content = b"pdf content here"
        file = SimpleUploadedFile("document.pdf", content)
        upload = create_upload_file(user, file)

        assert upload.status == UploadFile.Status.STORED
        assert upload.original_filename == "document.pdf"
        assert upload.size_bytes == len(content)
        assert upload.content_type == "application/pdf"
        assert upload.uploaded_by == user
        assert upload.sha256 == hashlib.sha256(content).hexdigest()
        assert upload.error_message == ""

    def test_oversized_upload_creates_failed_record(self, user, tmp_path, settings):
        """File exceeding max size creates UploadFile with status=FAILED."""
        settings.MEDIA_ROOT = tmp_path
        settings.FILE_UPLOAD_MAX_SIZE = 10
        file = SimpleUploadedFile("big.pdf", b"x" * 100)
        upload = create_upload_file(user, file)

        assert upload.status == UploadFile.Status.FAILED
        assert upload.content_type == "unknown"
        assert "exceeds maximum" in upload.error_message

    def test_upload_with_batch(self, user, tmp_path, settings):
        """Upload file can be associated with a batch."""
        settings.MEDIA_ROOT = tmp_path
        batch = UploadBatch.objects.create(created_by=user)
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_upload_file(user, file, batch=batch)

        assert upload.batch == batch
        assert upload.status == UploadFile.Status.STORED


@pytest.mark.django_db
class TestMarkFileProcessed:
    """Tests for mark_file_processed service."""

    def test_stored_to_processed(self, user, tmp_path, settings):
        """STORED file transitions to PROCESSED."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_upload_file(user, file)
        assert upload.status == UploadFile.Status.STORED

        result = mark_file_processed(upload)
        assert result.status == UploadFile.Status.PROCESSED

    def test_non_stored_raises_value_error(self, user, tmp_path, settings):
        """Non-STORED file raises ValueError."""
        settings.MEDIA_ROOT = tmp_path
        settings.FILE_UPLOAD_MAX_SIZE = 1
        file = SimpleUploadedFile("doc.pdf", b"content too large")
        upload = create_upload_file(user, file)
        assert upload.status == UploadFile.Status.FAILED

        with pytest.raises(ValueError, match="expected 'stored'"):
            mark_file_processed(upload)


@pytest.mark.django_db
class TestMarkFileFailed:
    """Tests for mark_file_failed service."""

    def test_sets_failed_with_error(self, user, tmp_path, settings):
        """Sets FAILED status with error message."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_upload_file(user, file)

        result = mark_file_failed(upload, error="Virus detected")
        assert result.status == UploadFile.Status.FAILED
        assert result.error_message == "Virus detected"


@pytest.mark.django_db
class TestMarkFileDeleted:
    """Tests for mark_file_deleted service."""

    def test_deletes_physical_file_and_sets_status(self, user, tmp_path, settings):
        """Deletes physical file and sets DELETED status."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_upload_file(user, file)
        file_path = tmp_path / upload.file.name

        result = mark_file_deleted(upload)
        assert result.status == UploadFile.Status.DELETED
        assert not file_path.exists()


@pytest.mark.django_db
class TestCreateBatch:
    """Tests for create_batch service."""

    def test_creates_batch_with_init_status(self, user):
        """Creates batch with INIT status."""
        batch = create_batch(user, idempotency_key="test-key")
        assert batch.status == UploadBatch.Status.INIT
        assert batch.created_by == user
        assert batch.idempotency_key == "test-key"


@pytest.mark.django_db
class TestFinalizeBatch:
    """Tests for finalize_batch service."""

    def test_all_stored_complete(self, user, tmp_path, settings):
        """All files STORED → batch COMPLETE."""
        settings.MEDIA_ROOT = tmp_path
        batch = UploadBatch.objects.create(created_by=user)
        for _ in range(3):
            file = SimpleUploadedFile("doc.pdf", b"content")
            create_upload_file(user, file, batch=batch)

        result = finalize_batch(batch)
        assert result.status == UploadBatch.Status.COMPLETE

    def test_mixed_statuses_partial(self, user, tmp_path, settings):
        """Mix of STORED and FAILED → batch PARTIAL."""
        settings.MEDIA_ROOT = tmp_path
        batch = UploadBatch.objects.create(created_by=user)

        file = SimpleUploadedFile("good.pdf", b"content")
        create_upload_file(user, file, batch=batch)

        settings.FILE_UPLOAD_MAX_SIZE = 1
        file = SimpleUploadedFile("bad.pdf", b"too large content")
        create_upload_file(user, file, batch=batch)

        settings.FILE_UPLOAD_MAX_SIZE = 52_428_800  # Reset
        result = finalize_batch(batch)
        assert result.status == UploadBatch.Status.PARTIAL

    def test_all_failed(self, user, tmp_path, settings):
        """All files FAILED → batch FAILED."""
        settings.MEDIA_ROOT = tmp_path
        settings.FILE_UPLOAD_MAX_SIZE = 1
        batch = UploadBatch.objects.create(created_by=user)

        for _ in range(2):
            file = SimpleUploadedFile("bad.pdf", b"too large")
            create_upload_file(user, file, batch=batch)

        result = finalize_batch(batch)
        assert result.status == UploadBatch.Status.FAILED


@pytest.mark.django_db
class TestCreateUploadFileOutboxEvent:
    """Tests for file.stored outbox event emission in create_upload_file."""

    def test_stored_file_emits_outbox_event(self, user, tmp_path, settings):
        """Successful upload emits file.stored outbox event with correct payload."""
        settings.MEDIA_ROOT = tmp_path
        content = b"test pdf content"
        file = SimpleUploadedFile("document.pdf", content)
        upload = create_upload_file(user, file)

        assert upload.status == UploadFile.Status.STORED
        event = OutboxEvent.objects.get(event_type="file.stored")
        assert event.aggregate_type == "UploadFile"
        assert event.aggregate_id == str(upload.pk)
        assert event.payload["file_id"] == str(upload.pk)
        assert event.payload["original_filename"] == "document.pdf"
        assert event.payload["content_type"] == "application/pdf"
        assert event.payload["size_bytes"] == len(content)
        assert event.payload["sha256"] == upload.sha256
        assert "url" in event.payload

    def test_failed_file_does_not_emit_outbox_event(self, user, tmp_path, settings):
        """Failed upload (oversized) does not create outbox event."""
        settings.MEDIA_ROOT = tmp_path
        settings.FILE_UPLOAD_MAX_SIZE = 10
        file = SimpleUploadedFile("big.pdf", b"x" * 100)
        upload = create_upload_file(user, file)

        assert upload.status == UploadFile.Status.FAILED
        assert not OutboxEvent.objects.filter(event_type="file.stored").exists()

    def test_outbox_event_idempotency_key(self, user, tmp_path, settings):
        """Outbox event idempotency key is 'UploadFile:{pk}'."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_upload_file(user, file)

        event = OutboxEvent.objects.get(event_type="file.stored")
        assert event.idempotency_key == f"UploadFile:{upload.pk}"


@pytest.mark.django_db
class TestNotifyExpiringFiles:
    """Tests for notify_expiring_files() service function."""

    def _create_old_upload(self, user, tmp_path, settings, hours_ago):
        """Helper to create an upload with a backdated created_at."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_upload_file(user, file)
        old_time = timezone.now() - timedelta(hours=hours_ago)
        UploadFile.objects.filter(pk=upload.pk).update(created_at=old_time)
        upload.refresh_from_db()
        return upload

    def test_notifies_files_within_window(self, user, tmp_path, settings):
        """File created >23h ago (with TTL=24h, notify=1h) gets notification."""
        upload = self._create_old_upload(user, tmp_path, settings, hours_ago=23.5)
        # Clear the file.stored event
        OutboxEvent.objects.filter(event_type="file.stored").delete()

        result = notify_expiring_files(ttl_hours=24, notify_hours=1)

        assert result["notified"] == 1
        event = OutboxEvent.objects.get(event_type="file.expiring")
        assert event.payload["file_id"] == str(upload.pk)

    def test_skips_files_outside_window(self, user, tmp_path, settings):
        """File created <23h ago does not get notification."""
        self._create_old_upload(user, tmp_path, settings, hours_ago=20)
        # Clear the file.stored event
        OutboxEvent.objects.filter(event_type="file.stored").delete()

        result = notify_expiring_files(ttl_hours=24, notify_hours=1)

        assert result["notified"] == 0
        assert not OutboxEvent.objects.filter(event_type="file.expiring").exists()

    def test_skips_non_stored_files(self, user, tmp_path, settings):
        """Files with status!=STORED are not notified."""
        upload = self._create_old_upload(user, tmp_path, settings, hours_ago=25)
        upload.status = UploadFile.Status.PROCESSED
        upload.save(update_fields=["status"])
        OutboxEvent.objects.filter(event_type="file.stored").delete()

        result = notify_expiring_files(ttl_hours=24, notify_hours=1)

        assert result["notified"] == 0

    def test_duplicate_notification_skipped(self, user, tmp_path, settings):
        """Calling twice for the same file skips on second call."""
        self._create_old_upload(user, tmp_path, settings, hours_ago=23.5)
        OutboxEvent.objects.filter(event_type="file.stored").delete()

        result1 = notify_expiring_files(ttl_hours=24, notify_hours=1)
        result2 = notify_expiring_files(ttl_hours=24, notify_hours=1)

        assert result1["notified"] == 1
        assert result2["notified"] == 0
        assert result2["skipped"] == 1

    def test_event_payload_includes_expires_at(self, user, tmp_path, settings):
        """Payload has 'expires_at' field."""
        self._create_old_upload(user, tmp_path, settings, hours_ago=23.5)
        OutboxEvent.objects.filter(event_type="file.stored").delete()

        notify_expiring_files(ttl_hours=24, notify_hours=1)

        event = OutboxEvent.objects.get(event_type="file.expiring")
        assert "expires_at" in event.payload
