"""
Pomodoro Focus Views.
Handles the timer interface and recording completed focus blocks towards daily streak.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone

from core.models import Student
from core.services import record_study_day, get_study_streak


STUDY_THOUGHTS = [
    "Small, focused steps add up to remarkable progress.",
    "You do not have to finish everything. Just begin the next thing.",
    "One quiet, focused session is a promise kept to your future self.",
    "Progress grows when you return to the work, one day at a time.",
    "Curiosity is a good reason to keep going.",
    "Give this moment your attention. The next step can wait.",
    "Every difficult idea gets easier with patient practice.",
]


def daily_study_thought():
    """Returns an inspiring daily study quotation that rotates per day."""
    return STUDY_THOUGHTS[timezone.localdate().toordinal() % len(STUDY_THOUGHTS)]


@login_required
def pomodoro_timer(request):
    """Renders the ambient Pomodoro Focus Studio interface."""
    if not hasattr(request.user, "student"):
        return redirect("login")
    return render(request, "pomodoro.html", {"daily_thought": daily_study_thought()})


@login_required
@require_POST
def complete_pomodoro_session(request):
    """Records a completed Pomodoro session and returns updated streak JSON."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    record_study_day(student)
    current_streak = get_study_streak(student)

    return JsonResponse({
        "success": True,
        "current_streak": current_streak,
        "message": "Focus session complete. Your study streak has been updated.",
    })
