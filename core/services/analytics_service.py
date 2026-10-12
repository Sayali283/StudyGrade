"""
Analytics Service.
Aggregates topic-level performance metrics and calculates personalized review recommendations.
"""
from django.db.models import Count, Q
from core.models import QuestionAnswer, Student


def get_topic_performance(student: Student) -> list[dict[str, int | str]]:
    """Returns question accuracy broken down by topic for the given student."""
    results = QuestionAnswer.objects.filter(
        question__quiz__student=student,
    ).values(
        "question__topic",
    ).annotate(
        attempts=Count("id"),
        correct=Count("id", filter=Q(is_correct=True)),
    ).order_by("question__topic")

    performance = []
    for result in results:
        attempts = result["attempts"]
        correct = result["correct"]
        performance.append({
            "topic": result["question__topic"],
            "attempts": attempts,
            "correct": correct,
            "accuracy": round(correct / attempts * 100) if attempts else 0,
        })
    return performance


def get_recommended_topic(performance: list[dict[str, int | str]]) -> dict[str, int | str] | None:
    """Finds the lowest accuracy topic with sufficient attempt history."""
    if not performance:
        return None

    established_topics = [t for t in performance if t["attempts"] >= 2]
    candidates = established_topics or performance
    return min(
        candidates,
        key=lambda t: (t["accuracy"], -t["attempts"], t["topic"]),
    )
