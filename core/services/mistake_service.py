"""
Mistake Notebook Service:
Handles recording of quiz mistakes, repetition tracking,
filtering, search, removal from revision, and mastery progression.
"""
import logging
from django.utils import timezone
from django.db.models import Q
from core.models import Student, Quiz, QuestionAnswer, MistakeRecord, Question

logger = logging.getLogger(__name__)


def record_quiz_mistakes(quiz: Quiz, student: Student) -> list[MistakeRecord]:
    """
    Scans submitted answers for a quiz and automatically creates or updates
    MistakeRecord entries for all incorrect questions.
    """
    wrong_answers = (
        QuestionAnswer.objects.filter(question__quiz=quiz, is_correct=False)
        .select_related("question")
    )

    records = []
    now = timezone.now()

    for item in wrong_answers:
        q = item.question
        topic = q.topic or quiz.subject
        selected = item.selected_answer or "No answer provided"
        correct = q.correct_answer
        explanation = q.explanation or ""

        # Check if this student already missed this question or exact question text
        existing = MistakeRecord.objects.filter(
            student=student,
            question_text=q.question_text,
        ).first()

        if existing:
            existing.mistake_count += 1
            existing.selected_answer = selected
            existing.correct_answer = correct
            existing.explanation = explanation or existing.explanation
            existing.status = "unresolved"
            existing.is_in_revision = True
            existing.question = q
            existing.last_missed_at = now
            # Next review is due today/tomorrow on repeated failure
            existing.next_review_at = now
            existing.save()
            records.append(existing)
        else:
            rec = MistakeRecord.objects.create(
                student=student,
                question=q,
                subject=quiz.subject,
                topic=topic,
                question_text=q.question_text,
                selected_answer=selected,
                correct_answer=correct,
                explanation=explanation,
                mistake_count=1,
                status="unresolved",
                is_in_revision=True,
                next_review_at=now,
            )
            records.append(rec)

    # Sync with Spaced Repetition engine
    try:
        from core.services.spaced_repetition_service import schedule_mistake_review
        for rec in records:
            schedule_mistake_review(rec)
    except Exception as err:
        logger.warning("Spaced repetition sync error for mistake records: %s", err)

    return records


def get_student_mistakes(
    student: Student,
    subject: str = "",
    topic: str = "",
    status: str = "",
    search_query: str = "",
    sort_by: str = "priority",
    include_removed: bool = False,
):
    """
    Returns filtered, searched, and sorted mistake records for the student.
    """
    qs = MistakeRecord.objects.filter(student=student)

    if not include_removed:
        qs = qs.filter(is_in_revision=True)

    if subject:
        qs = qs.filter(subject__iexact=subject)

    if topic:
        qs = qs.filter(topic__iexact=topic)

    if status and status in {"unresolved", "reviewing", "mastered"}:
        qs = qs.filter(status=status)

    if search_query:
        qs = qs.filter(
            Q(question_text__icontains=search_query)
            | Q(topic__icontains=search_query)
            | Q(subject__icontains=search_query)
            | Q(explanation__icontains=search_query)
        )

    if sort_by == "frequency":
        qs = qs.order_by("-mistake_count", "-last_missed_at")
    elif sort_by == "recent":
        qs = qs.order_by("-last_missed_at")
    elif sort_by == "due":
        qs = qs.order_by("next_review_at", "-mistake_count")
    else:  # 'priority': unresolved with high frequency first
        qs = qs.order_by(
            # Unresolved first, then reviewing, then mastered
            "status",
            "-mistake_count",
            "-last_missed_at",
        )

    return qs


def remove_mistake_from_revision(student: Student, mistake_id: int) -> bool:
    """
    Removes mistake from active revision list without deleting underlying quiz history.
    """
    mistake = MistakeRecord.objects.filter(id=mistake_id, student=student).first()
    if mistake:
        mistake.is_in_revision = False
        mistake.save(update_fields=["is_in_revision"])
        return True
    return False


def restore_mistake_to_revision(student: Student, mistake_id: int) -> bool:
    """Restores mistake back to active revision list."""
    mistake = MistakeRecord.objects.filter(id=mistake_id, student=student).first()
    if mistake:
        mistake.is_in_revision = True
        mistake.save(update_fields=["is_in_revision"])
        return True
    return False


def log_mistake_review(student: Student, mistake_id: int, was_correct: bool = False, notes_read_only: bool = False) -> MistakeRecord | None:
    """
    Tracks review activity for a mistake.
    Important rule: reading an explanation does NOT mark it mastered!
    Mastery only increments when answered correctly in practice.
    """
    mistake = MistakeRecord.objects.filter(id=mistake_id, student=student).first()
    if not mistake:
        return None

    now = timezone.now()
    mistake.last_reviewed_at = now

    if notes_read_only:
        # Merely reading explanation: keeps current status, but updates review timestamp
        mistake.save(update_fields=["last_reviewed_at"])
        return mistake

    if was_correct:
        if mistake.status == "unresolved":
            mistake.status = "reviewing"
        elif mistake.status == "reviewing":
            mistake.status = "mastered"
        # Push next review further out (3 days for reviewing, 7 days for mastered)
        days = 7 if mistake.status == "mastered" else 3
        mistake.next_review_at = now + timezone.timedelta(days=days)
    else:
        mistake.status = "unresolved"
        mistake.mistake_count += 1
        mistake.next_review_at = now + timezone.timedelta(days=1)

    mistake.save()
    return mistake
