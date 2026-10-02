from django.db.models import Count, Q

from .models import QuestionAnswer, Student


def get_topic_performance(student: Student) -> list[dict[str, int | str]]:
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
            "accuracy": round(correct / attempts * 100),
        })
    return performance


def get_recommended_topic(performance: list[dict[str, int | str]]) -> dict[str, int | str] | None:
    if not performance:
        return None

    established_topics = [topic for topic in performance if topic["attempts"] >= 2]
    candidates = established_topics or performance
    return min(
        candidates,
        key=lambda topic: (topic["accuracy"], -topic["attempts"], topic["topic"]),
    )