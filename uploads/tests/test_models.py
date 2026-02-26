"""Unit tests for upload models."""

import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from uploads.models import UploadBatch, UploadFile, UploadPart, UploadSession


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
            "processed",
            "failed",
            "deleted",
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
