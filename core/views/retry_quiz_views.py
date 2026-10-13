"""
Intelligent Retry Quiz Views:
Orchestrates targeted practice generation across 3 modes:
1. Quick Retry (3-5 questions)
2. Mistake Practice (unresolved mistakes)
3. Topic Mastery (configurable assessment)
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages as dj_messages

from core.models import Student, Notes, MistakeRecord
from core.services.retry_quiz_service import generate_retry_quiz


@login_required
def retry_quiz_setup(request):
    """
    Renders setup options for an Intelligent Retry Quiz or launches practice.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    initial_mode = request.GET.get("mode", "quick")
    selected_topic = request.GET.get("topic", "")
    selected_subject = request.GET.get("subject", "")
    mistake_id = request.GET.get("mistake_id")

    if request.method == "POST":
        mode = request.POST.get("mode", "quick")
        topic = request.POST.get("topic", "").strip()
        subject = request.POST.get("subject", "").strip()

        try:
            question_count = int(request.POST.get("question_count", "5"))
        except (ValueError, TypeError):
            question_count = 5

        raw_mistake_ids = request.POST.getlist("mistake_ids")
        mistake_ids = [int(mid) for mid in raw_mistake_ids if mid.isdigit()]
        if mistake_id and mistake_id.isdigit():
            mistake_ids.append(int(mistake_id))

        quiz = generate_retry_quiz(
            student=student,
            mode=mode,
            topic=topic,
            subject=subject,
            question_count=question_count,
            mistake_ids=mistake_ids if mistake_ids else None,
        )

        if not quiz:
            dj_messages.error(
                request,
                "Unable to generate practice questions for this selection. Try choosing another topic or uploading notes.",
            )
            return redirect("mistake_notebook")

        dj_messages.success(
            request,
            f"Generated {quiz.question_set.count()} targeted practice questions for {mode.title()} session!",
        )
        return redirect("take_quiz", quiz_id=quiz.id)

    # GET: render launcher page with student context
    unresolved_mistakes = MistakeRecord.objects.filter(student=student, status="unresolved", is_in_revision=True)
    distinct_topics = sorted(list(set(MistakeRecord.objects.filter(student=student).values_list("topic", flat=True))))
    notes = Notes.objects.filter(student=student)

    return render(request, "retry_quiz_setup.html", {
        "student": student,
        "initial_mode": initial_mode,
        "selected_topic": selected_topic,
        "selected_subject": selected_subject,
        "mistake_id": mistake_id,
        "unresolved_mistakes": unresolved_mistakes[:15],
        "distinct_topics": distinct_topics,
        "notes": notes,
    })


@login_required
@require_POST
def quick_retry_mistake(request, mistake_id):
    """
    Direct one-click launcher for practicing a specific mistake from Mistake Notebook.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    mistake = get_object_or_404(MistakeRecord, id=mistake_id, student=student)

    quiz = generate_retry_quiz(
        student=student,
        mode="mistakes",
        topic=mistake.topic,
        subject=mistake.subject,
        question_count=3,
        mistake_ids=[mistake.id],
    )

    if not quiz:
        dj_messages.warning(request, "Could not launch retry quiz for this mistake.")
        return redirect("mistake_notebook")

    return redirect("take_quiz", quiz_id=quiz.id)
