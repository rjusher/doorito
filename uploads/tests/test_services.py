"""Unit tests for ingest file services."""

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from uploads.models import IngestFile
from uploads.services.uploads import (
    consume_ingest_file,
    create_ingest_file,
    validate_file,
)


class TestValidateFile:
    """Tests for validate_file service."""

    def test_valid_file(self):
        """Valid file within size limit returns (mime_type, file_size)."""
        file = SimpleUploadedFile("report.pdf", b"fake pdf content")
        mime_type, file_size = validate_file(file)
        assert mime_type == "application/pdf"
        assert file_size == 16

    def test_file_exceeds_max_size(self):
        """File exceeding FILE_UPLOAD_MAX_SIZE raises ValidationError."""
        file = SimpleUploadedFile("big.pdf", b"x" * 100)
        with pytest.raises(ValidationError) as exc_info:
            validate_file(file, max_size=50)
        assert exc_info.value.code == "file_too_large"

    def test_unknown_extension_returns_octet_stream(self):
        """Unknown file extension returns application/octet-stream."""
        file = SimpleUploadedFile("data.xyz123", b"some data")
        mime_type, file_size = validate_file(file)
        assert mime_type == "application/octet-stream"
        assert file_size == 9

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
        mime_type, _file_size = validate_file(file)
        assert mime_type == "image/png"

    def test_custom_max_size_overrides_setting(self):
        """Custom max_size parameter overrides FILE_UPLOAD_MAX_SIZE."""
        file = SimpleUploadedFile("small.pdf", b"x" * 10)
        # Should pass with custom max_size=20
        _mime_type, file_size = validate_file(file, max_size=20)
        assert file_size == 10

        # Should fail with custom max_size=5
        with pytest.raises(ValidationError) as exc_info:
            validate_file(file, max_size=5)
        assert exc_info.value.code == "file_too_large"


class TestCreateIngestFile:
    """Tests for create_ingest_file service."""

    @pytest.mark.django_db
    def test_valid_upload_creates_ready_record(self, user, tmp_path, settings):
        """Valid file creates IngestFile with status=READY."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("document.pdf", b"pdf content here")
        upload = create_ingest_file(user, file)

        assert upload.status == IngestFile.Status.READY
        assert upload.original_filename == "document.pdf"
        assert upload.file_size == 16
        assert upload.mime_type == "application/pdf"
        assert upload.user == user
        assert upload.error_message == ""

    @pytest.mark.django_db
    def test_oversized_upload_creates_failed_record(self, user, tmp_path, settings):
        """File exceeding max size creates IngestFile with status=FAILED."""
        settings.MEDIA_ROOT = tmp_path
        settings.FILE_UPLOAD_MAX_SIZE = 10  # 10 bytes
        file = SimpleUploadedFile("big.pdf", b"x" * 100)
        upload = create_ingest_file(user, file)

        assert upload.status == IngestFile.Status.FAILED
        assert upload.mime_type == "unknown"
        assert "exceeds maximum" in upload.error_message

    @pytest.mark.django_db
    def test_upload_metadata_correct(self, user, tmp_path, settings):
        """Returned IngestFile has correct original_filename, file_size, mime_type."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("report.csv", b"a,b,c\n1,2,3")
        upload = create_ingest_file(user, file)

        assert upload.original_filename == "report.csv"
        assert upload.file_size == 11
        assert upload.mime_type == "text/csv"


class TestConsumeIngestFile:
    """Tests for consume_ingest_file service."""

    @pytest.mark.django_db
    def test_ready_upload_transitions_to_consumed(self, user, tmp_path, settings):
        """READY ingest file transitions to CONSUMED."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_ingest_file(user, file)
        assert upload.status == IngestFile.Status.READY

        result = consume_ingest_file(upload)
        assert result.status == IngestFile.Status.CONSUMED

    @pytest.mark.django_db
    def test_already_consumed_raises_value_error(self, user, tmp_path, settings):
        """Already CONSUMED ingest file raises ValueError."""
        settings.MEDIA_ROOT = tmp_path
        file = SimpleUploadedFile("doc.pdf", b"content")
        upload = create_ingest_file(user, file)
        consume_ingest_file(upload)

        with pytest.raises(ValueError, match="expected 'ready'"):
            consume_ingest_file(upload)

    @pytest.mark.django_db
    def test_failed_upload_raises_value_error(self, user, tmp_path, settings):
        """FAILED ingest file raises ValueError."""
        settings.MEDIA_ROOT = tmp_path
        settings.FILE_UPLOAD_MAX_SIZE = 1  # Force failure
        file = SimpleUploadedFile("doc.pdf", b"content that is too large")
        upload = create_ingest_file(user, file)
        assert upload.status == IngestFile.Status.FAILED

        with pytest.raises(ValueError, match="expected 'ready'"):
            consume_ingest_file(upload)
