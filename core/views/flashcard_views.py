"""
Flashcard Views.
Handles deck listing, automatic card generation, and interactive study sessions.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages as dj_messages
from django.db.models import Count

from core.models import Student, Notes
from core.services import (
    extract_document_text,
    generate_flashcard_items,
    get_study_streak,
    record_study_day,
)
from core.services.flashcard_service import save_flashcards_for_note


@login_required
def flashcard_home(request):
    """Lists study notes with their associated flashcard counts."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    notes = Notes.objects.filter(student=student).annotate(
        flashcard_count=Count("flashcards")
    ).order_by("subject")

    return render(request, "flashcard_home.html", {"notes": notes})


@login_required
def study_flashcards(request, note_id):
    """Renders the interactive 3D recall flashcard practice studio."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)
    cards = list(note.flashcards.all())
    flashcards_data = [
        {"front": card.front, "back": card.back}
        for card in cards
    ]

    return render(request, "flashcard_study.html", {
        "note": note,
        "cards": cards,
        "flashcards_data": flashcards_data,
    })


@login_required
@require_POST
def generate_flashcards(request, note_id):
    """Generates flashcards from study notes using AI or NLP heuristics."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)

    try:
        text = extract_document_text(note.file.path)
    except Exception as error:
        dj_messages.error(request, str(error))
        return redirect("flashcard_home")

    cards_data = generate_flashcard_items(text, note.subject)
    if not cards_data:
        dj_messages.error(request, "We could not find enough key points in this note to make flashcards.")
        return redirect("flashcard_home")

    count = save_flashcards_for_note(note, cards_data)
    dj_messages.success(request, f"Created {count} flashcards for {note.subject}.")
    return redirect("study_flashcards", note_id=note.id)


@login_required
@require_POST
def complete_flashcard_session(request, note_id):
    """Logs completion of a flashcard session and increments streak."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)
    if not note.flashcards.exists():
        dj_messages.error(request, "Generate flashcards before completing a study session.")
        return redirect("flashcard_home")

    record_study_day(student)
    streak = get_study_streak(student)
    dj_messages.success(
        request,
        f"Study session complete! Your current streak is {streak} day{'' if streak == 1 else 's'}.",
    )
    return redirect("study_flashcards", note_id=note.id)
