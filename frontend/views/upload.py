"""Upload view for the frontend app."""

import logging

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from uploads.models import UploadFile
from uploads.services.uploads import create_batch, create_upload_file, finalize_batch

from frontend.decorators import frontend_login_required

logger = logging.getLogger(__name__)

MAX_FILES_PER_REQUEST = 10


@frontend_login_required
@require_http_methods(["GET", "POST"])
def upload_view(request):
    """Upload page with drag-and-drop file upload interface."""
    if request.method == "GET":
        return render(request, "frontend/upload/index.html")

    # POST: process uploaded files
    files = request.FILES.getlist("files")

    if not files:
        error = "No files selected."
        if request.htmx:
            return render(
                request,
                "frontend/upload/partials/results.html",
                {"error": error},
            )
        messages.error(request, error)
        return redirect("frontend:upload")

    if len(files) > MAX_FILES_PER_REQUEST:
        error = f"Too many files. Maximum {MAX_FILES_PER_REQUEST} files per upload."
        if request.htmx:
            return render(
                request,
                "frontend/upload/partials/results.html",
                {"error": error},
            )
        messages.error(request, error)
        return redirect("frontend:upload")

    batch = create_batch(request.user)
    results = []
    for f in files:
        upload = create_upload_file(request.user, f, batch=batch)
        results.append(upload)
    finalize_batch(batch)

    stored_count = sum(1 for r in results if r.status == UploadFile.Status.STORED)
    failed_count = sum(1 for r in results if r.status == UploadFile.Status.FAILED)

    if request.htmx:
        return render(
            request,
            "frontend/upload/partials/results.html",
            {
                "results": results,
                "batch": batch,
                "stored_count": stored_count,
                "failed_count": failed_count,
            },
        )

    if failed_count == 0:
        messages.success(request, f"Uploaded {stored_count} file(s) successfully.")
    elif stored_count > 0:
        messages.warning(
            request,
            f"Uploaded {stored_count} file(s), {failed_count} failed.",
        )
    else:
        messages.error(request, f"All {failed_count} file(s) failed to upload.")

    return redirect("frontend:upload")
