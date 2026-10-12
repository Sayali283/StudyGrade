"""
Notes Management Views.
Handles note uploading, authorized document viewing, and note deletion.
"""
import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as dj_messages
from django.http import FileResponse, Http404

from core.models import Notes, Student
from core.forms import NotesForm


@login_required
def student_notes(request):
    """Lists student notes and handles document uploads."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    notes = Notes.objects.filter(student=student).order_by("-uploaded_at")

    if request.method == "POST":
        form = NotesForm(request.POST, request.FILES)
        if form.is_valid():
            note = form.save(commit=False)
            note.student = student
            note.save()
            dj_messages.success(request, f"Note '{note.subject}' uploaded successfully.")
            return redirect("student_notes")
        else:
            dj_messages.error(request, "Failed to upload note. Please choose a valid file.")
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
    Protects private study material from unauthorized access.
    """
    note = get_object_or_404(Notes, id=note_id)

    is_authorized = False
    if hasattr(request.user, "student") and note.student == request.user.student:
        is_authorized = True
    elif hasattr(request.user, "parent") and request.user.parent.student == note.student:
        is_authorized = True

    if not is_authorized:
        raise Http404("You do not have permission to view this note.")

    if not note.file or not os.path.exists(note.file.path):
        raise Http404("Note file was not found on the server.")

    ext = os.path.splitext(note.file.name)[1].lower()
    content_types = {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    content_type = content_types.get(ext, "application/octet-stream")

    return FileResponse(open(note.file.path, "rb"), content_type=content_type)


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
            print(f"[NotesView] Failed to delete file from disk: {err}")

    subject_name = note.subject
    note.delete()
    dj_messages.success(request, f"Note '{subject_name}' deleted successfully.")
    return redirect("student_notes")
