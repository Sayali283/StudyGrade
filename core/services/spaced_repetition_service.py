"""
Spaced Repetition & Daily Revision Service:
Implements adaptive interval scheduling heuristics, daily review dashboard metrics,
and concept recall tracking without duplicating review records.
"""
import logging
from datetime import date
from django.utils import timezone
from django.db.models import Count, Q

from core.models import Student, ScheduledReview, MistakeRecord, Notes, VisualFlowchart, ShortNote
from core.services.streak_service import record_study_day

logger = logging.getLogger(__name__)


def schedule_mistake_review(mistake: MistakeRecord) -> ScheduledReview:
    """
    Schedules or updates a Spaced Repetition review record for a quiz mistake.
    Guarantees uniqueness for (student, item_type, title, topic).
    """
    today = timezone.localdate()
    title = mistake.question_text[:120]

    review, created = ScheduledReview.objects.update_or_create(
        student=mistake.student,
        item_type="mistake",
        title=title,
        topic=mistake.topic,
        defaults={
            "subject": mistake.subject,
            "mistake_record": mistake,
            "content_payload": {
                "question": mistake.question_text,
                "selected_answer": mistake.selected_answer,
                "correct_answer": mistake.correct_answer,
                "explanation": mistake.explanation,
                "mistake_count": mistake.mistake_count,
            },
            "interval_days": 1.0,
            "next_review_date": today,
            "status": "due",
        },
    )
    return review


def schedule_concept_review(
    student: Student,
    concept_name: str,
    subject: str,
    topic: str,
    payload: dict,
    item_type: str = "concept",
    flowchart: VisualFlowchart | None = None,
    note: Notes | None = None,
) -> ScheduledReview:
    """
    Adds a concept from a visual diagram, short note, or flashcard to the revision schedule.
    Prevents duplicate records.
    """
    today = timezone.localdate()
    clean_title = concept_name.strip()[:255]

    review, _ = ScheduledReview.objects.update_or_create(
        student=student,
        item_type=item_type,
        title=clean_title,
        topic=topic or subject,
        defaults={
            "subject": subject,
            "flowchart": flowchart,
            "note": note,
            "content_payload": payload,
            "interval_days": 1.0,
            "next_review_date": today,
            "status": "due",
        },
    )
    return review


def process_review_attempt(
    review: ScheduledReview,
    was_correct: bool,
    confidence: str = "moderate",  # 'again', 'low', 'moderate', 'high'
) -> ScheduledReview:
    """
    Updates review interval using adaptive spaced repetition heuristics:
    - Incorrect: reset interval to 1 day, decrement ease factor, schedule today/tomorrow.
    - Low confidence: interval = 1 day.
    - Moderate confidence: interval = 3 days (or previous_interval * 1.5).
    - High confidence: interval = 7 days (or previous_interval * ease_factor).
    - Repeated success extends interval up to max 90 days.
    """
    now = timezone.now()
    today = timezone.localdate()

    review.last_reviewed_at = now
    review.review_count += 1

    if not was_correct or confidence == "again":
        review.consecutive_correct = 0
        review.interval_days = 1.0
        review.ease_factor = max(1.3, review.ease_factor - 0.2)
        review.status = "learning"
        review.next_review_date = today + timezone.timedelta(days=1)

        # Update linked mistake if present
        if review.mistake_record:
            from core.services.mistake_service import log_mistake_review
            log_mistake_review(review.student, review.mistake_record.id, was_correct=False)

    else:
        review.consecutive_correct += 1

        # Calculate new interval based on confidence level and history
        if confidence in {"low", "hard"}:
            new_interval = 1.0
        elif confidence in {"moderate", "good"}:
            if review.consecutive_correct == 1:
                new_interval = 3.0
            else:
                new_interval = max(3.0, review.interval_days * 1.5)
        elif confidence in {"high", "easy"}:
            if review.consecutive_correct == 1:
                new_interval = 7.0
            else:
                new_interval = max(7.0, review.interval_days * review.ease_factor)
                review.ease_factor = min(3.0, review.ease_factor + 0.1)
        else:
            new_interval = max(1.0, review.interval_days * review.ease_factor)

        # Cap max interval at 90 days
        review.interval_days = round(min(90.0, new_interval), 1)

        if review.consecutive_correct >= 3:
            review.status = "mastered"
        else:
            review.status = "learning"

        review.next_review_date = today + timezone.timedelta(days=int(review.interval_days))

        # Update linked mistake record
        if review.mistake_record:
            from core.services.mistake_service import log_mistake_review
            log_mistake_review(review.student, review.mistake_record.id, was_correct=True)

    review.save()

    # Track student study streak on completed review
    record_study_day(review.student)

    return review


def get_revision_today_summary(student: Student) -> dict:
    """
    Aggregates comprehensive metrics for the Revision Today dashboard:
    - Due today
    - Overdue reviews
    - Topics needing attention
    - Estimated revision time (2 mins per item)
    - Recently mastered topics
    """
    today = timezone.localdate()

    all_reviews = ScheduledReview.objects.filter(student=student)

    due_today_qs = all_reviews.filter(next_review_date__lte=today, status__in=["due", "learning"])
    overdue_qs = all_reviews.filter(next_review_date__lt=today, status__in=["due", "learning"])
    mastered_qs = all_reviews.filter(status="mastered").order_by("-last_reviewed_at")[:8]

    due_count = due_today_qs.count()
    overdue_count = overdue_qs.count()

    # Weak topics needing attention: topics with high due counts or repeated mistakes
    topics_needing_attention = (
        due_today_qs.values("topic", "subject")
        .annotate(item_count=Count("id"))
        .order_by("-item_count")[:5]
    )

    estimated_minutes = max(5, due_count * 2) if due_count > 0 else 0

    return {
        "due_count": due_count,
        "overdue_count": overdue_count,
        "total_active": all_reviews.exclude(status="mastered").count(),
        "mastered_count": all_reviews.filter(status="mastered").count(),
        "estimated_minutes": estimated_minutes,
        "due_items": due_today_qs.order_by("next_review_date", "-interval_days")[:30],
        "overdue_items": overdue_qs[:10],
        "mastered_items": mastered_qs,
        "topics_needing_attention": list(topics_needing_attention),
    }
