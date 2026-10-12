"""
Streak Service.
Calculates and updates consecutive active study days for a student.
"""
from datetime import date, timedelta
from django.utils import timezone

from core.models import Student, StudyDay


def record_study_day(student: Student, study_date: date | None = None) -> StudyDay:
    """Records an active study day for the student if not already present."""
    study_date = study_date or timezone.localdate()
    study_day, _ = StudyDay.objects.get_or_create(
        student=student,
        study_date=study_date,
    )
    return study_day


def get_study_streak(student: Student, today: date | None = None) -> int:
    """Calculates the consecutive active study streak ending today or yesterday."""
    today = today or timezone.localdate()
    study_dates = sorted(
        StudyDay.objects.filter(student=student).values_list("study_date", flat=True),
        reverse=True,
    )
    study_dates = [sd for sd in study_dates if sd <= today]

    if not study_dates:
        return 0

    latest_date = study_dates[0]
    if latest_date < today - timedelta(days=1):
        return 0

    streak = 0
    expected_date = latest_date
    for study_date in study_dates:
        if study_date == expected_date:
            streak += 1
            expected_date -= timedelta(days=1)
        elif study_date < expected_date:
            break

    return streak
