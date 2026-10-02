from datetime import date, timedelta

from django.utils import timezone

from .models import StudyDay, Student


def record_study_day(student: Student, study_date: date | None = None) -> StudyDay:
    study_date = study_date or timezone.localdate()
    study_day, _ = StudyDay.objects.get_or_create(
        student=student,
        study_date=study_date,
    )
    return study_day


def get_study_streak(student: Student, today: date | None = None) -> int:
    today = today or timezone.localdate()
    study_dates = StudyDay.objects.filter(
        student=student,
    ).values_list("study_date", flat=True)

    latest_date = study_dates.first()
    if latest_date is None or latest_date < today - timedelta(days=1):
        return 0

    streak = 0
    expected_date = latest_date
    for study_date in study_dates:
        if study_date != expected_date:
            break
        streak += 1
        expected_date -= timedelta(days=1)

    return streak