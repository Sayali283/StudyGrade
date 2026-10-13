"""
Spaced Repetition & Revision Today Views:
Displays the daily revision dashboard, interactive recall sessions,
and endpoints to schedule or record review mastery.
"""
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages as dj_messages
from django.http import JsonResponse
from django.utils import timezone

from core.models import Student, ScheduledReview, Notes, VisualFlowchart
from core.services.spaced_repetition_service import (
    get_revision_today_summary,
    process_review_attempt,
    schedule_concept_review,
)


@login_required
def revision_today(request):
    """
    Renders the Revision Today command center:
    Due today count, overdue count, time estimate, topics needing attention,
    recently mastered items, and launch button.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        if hasattr(request.user, "parent"):
            student = request.user.parent.student
        else:
            return redirect("login")

    summary = get_revision_today_summary(student)

    return render(request, "revision_today.html", {
        "student": student,
        "summary": summary,
    })


@login_required
def start_revision_session(request):
    """
    Active recall study session stepping student through items due for review today.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    today = timezone.localdate()
    due_reviews = ScheduledReview.objects.filter(
        student=student,
        next_review_date__lte=today,
        status__in=["due", "learning"],
    ).order_by("next_review_date", "-interval_days")

    if not due_reviews.exists():
        dj_messages.info(request, "All caught up! No reviews due right now.")
        return redirect("revision_today")

    return render(request, "revision_session.html", {
        "student": student,
        "reviews": due_reviews,
        "total_items": due_reviews.count(),
    })


@login_required
@require_POST
def submit_review_feedback(request, review_id):
    """
    AJAX endpoint: evaluates recall outcome and updates Spaced Repetition interval.
    Expects POST confidence: 'again', 'low', 'moderate', or 'high'.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    review = get_object_or_404(ScheduledReview, id=review_id, student=student)
    confidence = request.POST.get("confidence", "moderate").lower()
    if confidence not in {"again", "low", "moderate", "high"}:
        confidence = "moderate"

    was_correct = confidence != "again"

    updated = process_review_attempt(review, was_correct=was_correct, confidence=confidence)

    return JsonResponse({
        "success": True,
        "review_id": updated.id,
        "new_interval_days": updated.interval_days,
        "next_review_date": updated.next_review_date.strftime("%b %d, %Y"),
        "status": updated.status,
        "consecutive_correct": updated.consecutive_correct,
    })


@login_required
@require_POST
def add_concept_to_revision(request):
    """
    AJAX endpoint: adds any concept from a diagram node, note, or flashcard
    to the student's Spaced Repetition schedule.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    concept_name = (request.POST.get("concept_name") or "").strip()
    subject = (request.POST.get("subject") or "General").strip()
    topic = (request.POST.get("topic") or subject).strip()
    explanation = (request.POST.get("explanation") or "").strip()
    item_type = request.POST.get("item_type", "concept")

    if not concept_name:
        return JsonResponse({"error": "Concept name is required."}, status=400)

    flowchart_id = request.POST.get("flowchart_id")
    flowchart = VisualFlowchart.objects.filter(id=flowchart_id).first() if flowchart_id else None

    note_id = request.POST.get("note_id")
    note = Notes.objects.filter(id=note_id).first() if note_id else None

    payload = {
        "concept": concept_name,
        "explanation": explanation,
        "source": request.POST.get("source_passage", ""),
    }

    review = schedule_concept_review(
        student=student,
        concept_name=concept_name,
        subject=subject,
        topic=topic,
        payload=payload,
        item_type=item_type,
        flowchart=flowchart,
        note=note,
    )

    return JsonResponse({
        "success": True,
        "message": f"'{concept_name}' added to your Daily Revision queue!",
        "review_id": review.id,
        "next_review_date": review.next_review_date.strftime("%b %d, %Y"),
    })
