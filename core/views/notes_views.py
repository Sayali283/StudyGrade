"""
Notes Management Views.
Handles note uploading with per-user storage quotas, authorized document streaming,
and note deletion.
"""
import os
import logging
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as dj_messages
from django.http import FileResponse, Http404
from django.db.models import Sum

from core.models import Notes, Student
from core.forms import NotesForm

logger = logging.getLogger(__name__)


@login_required
def student_notes(request):
    """Lists student notes and handles document uploads with quota enforcement."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    notes = Notes.objects.filter(student=student).order_by("-uploaded_at")

    if request.method == "POST":
        form = NotesForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data["file"]
            file_size = uploaded_file.size

            max_user_quota = getattr(settings, "MAX_USER_STORAGE_BYTES", 50 * 1024 * 1024)
            current_total = (
                Notes.objects.filter(student=student).aggregate(total=Sum("file_size"))["total"]
                or 0
            )

            if current_total + file_size > max_user_quota:
                quota_mb = max_user_quota // (1024 * 1024)
                current_mb = round(current_total / (1024 * 1024), 1)
                dj_messages.error(
                    request,
                    f"Storage quota exceeded. Your account has used {current_mb} MB of the allowed {quota_mb} MB quota. "
                    "Please delete older documents before uploading new ones."
                )
            else:
                note = form.save(commit=False)
                note.student = student
                note.file_size = file_size
                note.save()
                dj_messages.success(request, f"Note '{note.subject}' uploaded successfully.")
                return redirect("student_notes")
        else:
            for field, error_list in form.errors.items():
                for error_msg in error_list:
                    dj_messages.error(request, error_msg)
    else:
        form = NotesForm()

    return render(request, "student_notes.html", {
        "notes": notes,
        "form": form,
    })


@login_required
def view_note(request, note_id):
    """
    Securely streams note file content with student & parent authorization.
    Protects private study material from unauthorized access across storage backends.
    """
    note = get_object_or_404(Notes, id=note_id)

    is_authorized = False
    if hasattr(request.user, "student") and note.student == request.user.student:
        is_authorized = True
    elif hasattr(request.user, "parent") and request.user.parent.student == note.student:
        is_authorized = True

    if not is_authorized:
        raise Http404("You do not have permission to view this note.")

    if not note.file:
        raise Http404("Note file was not found on the server.")

    ext = os.path.splitext(note.file.name)[1].lower()
    content_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/plain",
        ".markdown": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    try:
        file_handle = note.file.open("rb")
        return FileResponse(file_handle, content_type=content_type)
    except Exception as err:
        logger.error("Failed to open note file #%s: %s", note.id, err)
        raise Http404("Note file was not found on the server.")


@login_required
def delete_note(request, note_id):
    """Deletes a note owned by the authenticated student."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)

    if note.file:
        try:
            note.file.delete(save=False)
        except Exception as err:
            logger.warning("Failed to delete file from storage: %s", err)

    subject_name = note.subject
    note.delete()
    dj_messages.success(request, f"Note '{subject_name}' deleted successfully.")
    return redirect("student_notes")

