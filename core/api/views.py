"""
RESTful API views for StudyGrade (v1).
Provides standardized JSON responses with error handling and authentication.
"""
from functools import wraps
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST

from core.models import Student, Notes, Quiz
from core.services import (
    get_study_streak,
    record_study_day,
    get_topic_performance,
    get_recommended_topic,
)


def api_success(data=None, message="Success", status=200):
    """Formats standardized success response."""
    return JsonResponse({
        "status": "success",
        "message": message,
        "data": data or {},
    }, status=status)


def api_error(message="An error occurred", code="BAD_REQUEST", status=400):
    """Formats standardized error response."""
    return JsonResponse({
        "status": "error",
        "code": code,
        "message": message,
    }, status=status)


def api_login_required(view_func):
    """Ensures request is authenticated, returning a 401 JSON error instead of redirecting."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return api_error("Authentication required.", code="UNAUTHORIZED", status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped_view


@require_http_methods(["GET"])
def health_check(request):
    """API health check probe for load balancers and status monitors."""
    return api_success({"status": "healthy", "service": "StudyGrade API v1"})


@api_login_required
@require_http_methods(["GET"])
def get_streak_api(request):
    """Returns current active streak for the authenticated student."""
    student = Student.objects.filter(user=request.user).first()
    if not student:
        return api_error("Only student accounts can track study streaks.", code="FORBIDDEN", status=403)

    streak = get_study_streak(student)
    return api_success({
        "current_streak": streak,
        "unit": "day" if streak == 1 else "days",
    })


@api_login_required
@require_http_methods(["GET"])
def get_analytics_api(request):
    """Returns topic accuracy metrics and next recommended study topic."""
    student = Student.objects.filter(user=request.user).first()
    if not student:
        return api_error("Only student accounts have analytics.", code="FORBIDDEN", status=403)

    topic_performance = get_topic_performance(student)
    recommended_topic = get_recommended_topic(topic_performance)

    return api_success({
        "topic_performance": topic_performance,
        "recommended_topic": recommended_topic,
    })


@api_login_required
@require_POST
def record_focus_block_api(request):
    """Records a completed Pomodoro block and increments streak."""
    student = Student.objects.filter(user=request.user).first()
    if not student:
        return api_error("Only student accounts can record focus blocks.", code="FORBIDDEN", status=403)

    record_study_day(student)
    new_streak = get_study_streak(student)

    return api_success({
        "current_streak": new_streak,
    }, message="Focus session recorded successfully.")


@api_login_required
@require_http_methods(["GET"])
def list_student_notes_api(request):
    """Returns a list of notes uploaded by the student."""
    student = Student.objects.filter(user=request.user).first()
    if not student:
        return api_error("Unauthorized.", code="FORBIDDEN", status=403)

    notes = Notes.objects.filter(student=student).values("id", "subject", "uploaded_at")
    return api_success({"notes": list(notes)})


@api_login_required
@require_http_methods(["GET"])
def get_flashcards_api(request, note_id):
    """Returns flashcards belonging to the specified note."""
    student = Student.objects.filter(user=request.user).first()
    if not student:
        return api_error("Unauthorized.", code="FORBIDDEN", status=403)

    note = Notes.objects.filter(id=note_id, student=student).first()
    if not note:
        return api_error("Note not found.", code="NOT_FOUND", status=404)

    cards = list(note.flashcards.values("id", "front", "back", "created_at"))
    return api_success({"subject": note.subject, "flashcards": cards})
