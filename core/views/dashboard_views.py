"""
Dashboard and Analytics Views.
Handles metrics compilation for student and parent dashboards, and topic progress visualization.
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

from core.models import Student, Notes, Quiz, StudyDay
from core.services import (
    get_study_streak,
    get_topic_performance,
    get_recommended_topic,
)
from core.views.pomodoro_views import daily_study_thought


@login_required
def student_dashboard(request):
    """Renders student overview with streaks, note counts, and recent scores."""
    if not hasattr(request.user, "student"):
        return redirect("login")

    student = request.user.student
    total_notes = Notes.objects.filter(student=student).count()
    quizzes = Quiz.objects.filter(student=student)
    total_quizzes = quizzes.count()

    scores = [q.score for q in quizzes if q.score is not None]
    avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0

    last_quiz = quizzes.order_by("-date").first()
    last_score = last_quiz.score if last_quiz else 0.0

    return render(request, "student_dashboard.html", {
        "student": student,
        "total_notes": total_notes,
        "total_quizzes": total_quizzes,
        "avg_score": avg_score,
        "last_score": last_score,
        "current_streak": get_study_streak(student),
        "last_study_day": StudyDay.objects.filter(student=student).first(),
        "daily_thought": daily_study_thought(),
    })


@login_required
def parent_dashboard(request):
    """Renders parent view of linked student's performance and activity streak."""
    if not hasattr(request.user, "parent"):
        return redirect("login")

    student = request.user.parent.student
    quizzes = Quiz.objects.filter(student=student).order_by("date")
    scores = list(quizzes.values_list("score", flat=True))
    total_quizzes = quizzes.count()

    avg_score = round(sum(scores) / total_quizzes, 2) if total_quizzes else 0.0
    best_score = max(scores) if scores else 0.0
    worst_score = min(scores) if scores else 0.0

    return render(request, "parent_dashboard.html", {
        "student": student,
        "quizzes": quizzes,
        "scores": scores,
        "total_quizzes": total_quizzes,
        "average_score": avg_score,
        "best_score": best_score,
        "worst_score": worst_score,
        "current_streak": get_study_streak(student),
        "last_study_day": StudyDay.objects.filter(student=student).first(),
    })


@login_required
def student_progress(request):
    """Displays mastery charts, performance distribution, and focus recommendations."""
    if not hasattr(request.user, "student"):
        return redirect("login")

    student = request.user.student
    quizzes = Quiz.objects.filter(student=student).order_by("date")
    total_quizzes = quizzes.count()

    scores = [q.score for q in quizzes if q.score is not None]
    average_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    best_score = max(scores) if scores else 0.0
    worst_score = min(scores) if scores else 0.0

    topic_performance = get_topic_performance(student)
    recommended_topic = get_recommended_topic(topic_performance)

    return render(request, "student_progress.html", {
        "quizzes": quizzes,
        "total_quizzes": total_quizzes,
        "average_score": average_score,
        "best_score": best_score,
        "worst_score": worst_score,
        "topic_performance": topic_performance,
        "recommended_topic": recommended_topic,
        "topic_chart_data": [
            {"topic": item["topic"], "accuracy": item["accuracy"]}
            for item in topic_performance
        ],
    })
