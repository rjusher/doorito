"""Unit tests for upload session services."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from uploads.models import UploadFile, UploadSession
from uploads.services.sessions import (
    complete_upload_session,
    create_upload_session,
    record_upload_part,
)


@pytest.fixture
def upload_file(user, tmp_path, settings):
    """Create an UploadFile for session tests."""
    settings.MEDIA_ROOT = tmp_path
    file = SimpleUploadedFile("test.pdf", b"content")
    return UploadFile.objects.create(
        uploaded_by=user,
        file=file,
        original_filename="test.pdf",
        content_type="application/pdf",
        size_bytes=7,
        status=UploadFile.Status.UPLOADING,
    )


@pytest.mark.django_db
class TestCreateUploadSession:
    """Tests for create_upload_session service."""

    def test_default_chunk_size(self, upload_file):
        """Default chunk size is 5 MB."""
        session = create_upload_session(upload_file, total_size_bytes=10_000_000)
        assert session.chunk_size_bytes == 5_242_880
        assert session.total_parts == 2
        assert session.total_size_bytes == 10_000_000
        assert session.status == UploadSession.Status.INIT

    def test_custom_chunk_size(self, upload_file):
        """Custom chunk size calculates correct total_parts."""
        session = create_upload_session(
            upload_file,
            total_size_bytes=1000,
            chunk_size_bytes=300,
        )
        assert session.chunk_size_bytes == 300
        assert session.total_parts == 4  # ceil(1000/300)


@pytest.mark.django_db
class TestRecordUploadPart:
    """Tests for record_upload_part service."""

    def test_records_part_with_received_status(self, upload_file):
        """Records a part with RECEIVED status."""
        session = create_upload_session(upload_file, total_size_bytes=1000)
        part = record_upload_part(
            session,
            part_number=1,
            offset_bytes=0,
            size_bytes=500,
        )
        assert part.status == "received"
        assert part.part_number == 1
        assert part.offset_bytes == 0
        assert part.size_bytes == 500

    def test_updates_session_counters(self, upload_file):
        """Recording a part updates session progress counters."""
        session = create_upload_session(upload_file, total_size_bytes=1000)
        record_upload_part(session, part_number=1, offset_bytes=0, size_bytes=500)

        session.refresh_from_db()
        assert session.completed_parts == 1
        assert session.bytes_received == 500
        assert session.status == UploadSession.Status.IN_PROGRESS


@pytest.mark.django_db
class TestCompleteUploadSession:
    """Tests for complete_upload_session service."""

    def test_all_parts_received_completes(self, upload_file):
        """All parts received → session COMPLETE, file STORED."""
        session = create_upload_session(
            upload_file,
            total_size_bytes=1000,
            chunk_size_bytes=500,
        )
        record_upload_part(session, part_number=1, offset_bytes=0, size_bytes=500)
        record_upload_part(session, part_number=2, offset_bytes=500, size_bytes=500)

        result = complete_upload_session(session)
        assert result.status == UploadSession.Status.COMPLETE

        upload_file.refresh_from_db()
        assert upload_file.status == UploadFile.Status.STORED

    def test_missing_parts_raises_value_error(self, upload_file):
        """Missing parts raises ValueError."""
        session = create_upload_session(
            upload_file,
            total_size_bytes=1000,
            chunk_size_bytes=500,
        )
        record_upload_part(session, part_number=1, offset_bytes=0, size_bytes=500)

        with pytest.raises(ValueError, match="received 1 of 2 parts"):
            complete_upload_session(session)
