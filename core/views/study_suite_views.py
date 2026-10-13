"""
Study Suite Views:
Handles interactive Flowcharts, Cornell Notes & Cheat Sheets, and Quiz Remediation.
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as dj_messages
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST

from core.models import Notes, Student, Quiz, RemediationReview
from core.services.study_suite_service import (
    generate_flowchart_for_note,
    generate_shortnotes_for_note,
    generate_quiz_remediation,
)


def _check_note_access(request, note):
    """Verifies that the logged in user is the owner student or linked parent."""
    if hasattr(request.user, "student") and note.student == request.user.student:
        return True
    if hasattr(request.user, "parent") and request.user.parent.student == note.student:
        return True
    return False


@login_required
def note_flowchart(request, note_id):
    """
    Renders an interactive Mermaid.js flowchart/mindmap for the selected note.
    Supports dynamic diagram type switching (flowchart, mindmap, sequence).
    """
    note = get_object_or_404(Notes, id=note_id)
    if not _check_note_access(request, note):
        raise Http404("You do not have permission to view this note's flowchart.")

    diagram_type = request.GET.get("type", "flowchart").lower()
    if diagram_type not in {"flowchart", "mindmap", "sequence"}:
        diagram_type = "flowchart"

    force_refresh = request.GET.get("refresh") == "1"

    chart = generate_flowchart_for_note(
        note=note,
        diagram_type=diagram_type,
        force_refresh=force_refresh,
    )

    return render(request, "note_flowchart.html", {
        "note": note,
        "chart": chart,
        "current_type": diagram_type,
    })


@login_required
def note_shortnotes(request, note_id):
    """
    Renders structured Cornell revision notes, executive summary,
    high-yield definitions, and memory mnemonics.
    """
    note = get_object_or_404(Notes, id=note_id)
    if not _check_note_access(request, note):
        raise Http404("You do not have permission to view this note's revision guide.")

    force_refresh = request.GET.get("refresh") == "1"
    short_note = generate_shortnotes_for_note(note=note, force_refresh=force_refresh)

    return render(request, "note_shortnotes.html", {
        "note": note,
        "short_note": short_note,
    })


@login_required
def quiz_remediation(request, quiz_id):
    """
    Renders AI-powered remediation workout analyzing incorrect answers
    and offering targeted concept clarity with interactive mastery verification.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        if hasattr(request.user, "parent"):
            student = request.user.parent.student
        else:
            return redirect("login")

    quiz = get_object_or_404(Quiz, id=quiz_id, student=student)
    remediations = generate_quiz_remediation(quiz=quiz, student=student)

    resolved_count = sum(1 for r in remediations if r.is_resolved)
    total_count = len(remediations)

    return render(request, "quiz_remediation.html", {
        "quiz": quiz,
        "remediations": remediations,
        "resolved_count": resolved_count,
        "total_count": total_count,
    })


@login_required
@require_POST
def resolve_remediation(request, remediation_id):
    """
    AJAX endpoint: Evaluates student's answer to a remediation micro-practice item.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    remed = get_object_or_404(RemediationReview, id=remediation_id, student=student)
    selected_option = (request.POST.get("selected_option") or "").strip()

    is_correct = (selected_option == remed.correct_answer)
    if is_correct:
        remed.is_resolved = True
        remed.save(update_fields=["is_resolved"])

    return JsonResponse({
        "success": True,
        "is_correct": is_correct,
        "correct_answer": remed.correct_answer,
        "explanation": remed.explanation,
        "is_resolved": remed.is_resolved,
    })
