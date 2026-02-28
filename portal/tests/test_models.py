"""Unit tests for upload models."""

import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from portal.models import (
    PortalEventOutbox,
    UploadBatch,
    UploadFile,
    UploadPart,
    UploadSession,
)


@pytest.mark.django_db
class TestUUIDv7PrimaryKeys:
    """Verify all models use UUID v7 primary keys."""

    def test_upload_batch_uuid7_pk(self, user):
        batch = UploadBatch.objects.create(created_by=user)
        assert isinstance(batch.pk, uuid.UUID)
        assert batch.pk.version == 7

    def test_upload_file_uuid7_pk(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        assert isinstance(upload.pk, uuid.UUID)
        assert upload.pk.version == 7

    def test_upload_session_uuid7_pk(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        session = UploadSession.objects.create(
            file=upload,
            total_size_bytes=1000,
            total_parts=1,
        )
        assert isinstance(session.pk, uuid.UUID)
        assert session.pk.version == 7

    def test_upload_part_uuid7_pk(self, user, tmp_path, settings):
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        session = UploadSession.objects.create(
            file=upload,
            total_size_bytes=1000,
            total_parts=1,
        )
        part = UploadPart.objects.create(
            session=session,
            part_number=1,
            offset_bytes=0,
            size_bytes=1000,
        )
        assert isinstance(part.pk, uuid.UUID)
        assert part.pk.version == 7


@pytest.mark.django_db
class TestCascadeRules:
    """Verify FK cascade behavior."""

    def test_delete_user_sets_null_on_upload_file(self, user, tmp_path, settings):
        """SET_NULL: deleting user nullifies uploaded_by."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        user.delete()
        upload.refresh_from_db()
        assert upload.uploaded_by is None

    def test_delete_batch_sets_null_on_upload_file(self, user, tmp_path, settings):
        """SET_NULL: deleting batch nullifies file.batch."""
        settings.MEDIA_ROOT = tmp_path
        batch = UploadBatch.objects.create(created_by=user)
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            batch=batch,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        batch.delete()
        upload.refresh_from_db()
        assert upload.batch is None

    def test_delete_upload_file_cascades_to_session(self, user, tmp_path, settings):
        """CASCADE: deleting file deletes session."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        session = UploadSession.objects.create(
            file=upload,
            total_size_bytes=1000,
            total_parts=1,
        )
        upload.delete()
        assert not UploadSession.objects.filter(pk=session.pk).exists()

    def test_delete_session_cascades_to_parts(self, user, tmp_path, settings):
        """CASCADE: deleting session deletes parts."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        session = UploadSession.objects.create(
            file=upload,
            total_size_bytes=1000,
            total_parts=2,
        )
        part = UploadPart.objects.create(
            session=session,
            part_number=1,
            offset_bytes=0,
            size_bytes=500,
        )
        session.delete()
        assert not UploadPart.objects.filter(pk=part.pk).exists()


@pytest.mark.django_db
class TestConstraints:
    """Verify model constraints."""

    def test_unique_session_part_number(self, user, tmp_path, settings):
        """Duplicate (session, part_number) raises IntegrityError."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        session = UploadSession.objects.create(
            file=upload,
            total_size_bytes=1000,
            total_parts=2,
        )
        UploadPart.objects.create(
            session=session,
            part_number=1,
            offset_bytes=0,
            size_bytes=500,
        )
        with pytest.raises(IntegrityError):
            UploadPart.objects.create(
                session=session,
                part_number=1,
                offset_bytes=500,
                size_bytes=500,
            )


@pytest.mark.django_db
class TestModelDefaults:
    """Verify model default values."""

    def test_upload_file_metadata_default(self, user, tmp_path, settings):
        """New UploadFile has metadata == {}."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("test.pdf", b"content")
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename="test.pdf",
            content_type="application/pdf",
            size_bytes=7,
        )
        assert upload.metadata == {}

    def test_status_choices(self):
        """Verify expected status values for each model."""
        assert set(UploadBatch.Status.values) == {
            "init",
            "in_progress",
            "complete",
            "partial",
            "failed",
        }
        assert set(UploadFile.Status.values) == {
            "uploading",
            "stored",
            "failed",
        }
        assert set(UploadSession.Status.values) == {
            "init",
            "in_progress",
            "complete",
            "failed",
            "aborted",
        }
        assert set(UploadPart.Status.values) == {
            "pending",
            "received",
            "failed",
        }


@pytest.mark.django_db
class TestPortalEventOutboxUUID7PK:
    """Verify PortalEventOutbox uses UUID v7 primary key."""

    def test_uuid7_pk(self):
        entry = PortalEventOutbox.objects.create(
            aggregate_type="UploadFile",
            aggregate_id="test-id",
            event_type="file.stored",
            idempotency_key="key1",
        )
        assert isinstance(entry.pk, uuid.UUID)
        assert entry.pk.version == 7


@pytest.mark.django_db
class TestPortalEventOutboxStatusChoices:
    """Verify PortalEventOutbox status choices."""

    def test_status_choices(self):
        assert set(PortalEventOutbox.Status.values) == {
            "pending",
            "delivered",
            "failed",
        }


@pytest.mark.django_db
class TestPortalEventOutboxUniqueConstraint:
    """Verify unique constraint on (event_type, idempotency_key)."""

    def test_duplicate_raises_integrity_error(self):
        PortalEventOutbox.objects.create(
            aggregate_type="UploadFile",
            aggregate_id="id1",
            event_type="file.stored",
            idempotency_key="key1",
        )
        with pytest.raises(IntegrityError):
            PortalEventOutbox.objects.create(
                aggregate_type="UploadFile",
                aggregate_id="id2",
                event_type="file.stored",
                idempotency_key="key1",
            )


@pytest.mark.django_db
class TestPortalEventOutboxDefaults:
    """Verify PortalEventOutbox default values."""

    def test_defaults(self):
        entry = PortalEventOutbox.objects.create(
            aggregate_type="UploadFile",
            aggregate_id="test-id",
            event_type="file.stored",
            idempotency_key="key1",
        )
        assert entry.status == "pending"
        assert entry.attempts == 0
        assert entry.max_attempts == 5
        assert entry.payload == {}
        assert entry.delivered_at is None
        assert entry.error_message == ""


@pytest.mark.django_db
class TestPortalEventOutboxStr:
    """Verify PortalEventOutbox __str__ method."""

    def test_str_format(self):
        entry = PortalEventOutbox.objects.create(
            aggregate_type="UploadFile",
            aggregate_id="test-id",
            event_type="file.stored",
            idempotency_key="key1",
        )
        assert str(entry) == "file.stored (Pending)"


@pytest.mark.django_db
class TestAdminRegistration:
    """Verify all portal models are registered in admin."""

    def test_all_portal_models_registered(self):
        from django.contrib.admin.sites import site

        for model in [
            UploadBatch,
            UploadFile,
            UploadSession,
            UploadPart,
            PortalEventOutbox,
        ]:
            assert model in site._registry, f"{model.__name__} not registered in admin"
