"""
Quiz Views.
Handles quiz listing, question generation, quiz-taking, and review rendering.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages as dj_messages

from core.models import Student, Notes, Quiz, Question
from core.services import (
    extract_document_text,
    generate_quiz_questions,
    evaluate_quiz_submission,
    record_study_day,
)


@login_required
def quiz_home(request):
    """Displays the student's quiz dashboard and past attempt history."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    notes = Notes.objects.filter(student=student)
    quizzes = Quiz.objects.filter(student=student).order_by("-date")

    return render(request, "quiz_home.html", {
        "notes": notes,
        "quizzes": quizzes,
    })


@login_required
@require_POST
def generate_quiz(request, note_id):
    """Generates MCQs from uploaded notes using AI or NLP service."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    try:
        question_count = int(request.POST.get("question_count", "5"))
    except (TypeError, ValueError):
        question_count = 0

    if question_count not in {5, 10, 20, 30}:
        dj_messages.error(request, "Please choose 5, 10, 20, or 30 questions.")
        return redirect("quiz_home")

    note = get_object_or_404(Notes, id=note_id, student=student)

    try:
        text = extract_document_text(note.file.path)
    except Exception as error:
        dj_messages.error(request, str(error))
        return redirect("quiz_home")

    questions_data = generate_quiz_questions(
        text=text,
        question_count=question_count,
        default_topic=note.subject,
    )

    if not questions_data:
        dj_messages.error(request, "Could not generate questions from this note. Please provide longer study notes.")
        return redirect("quiz_home")

    quiz = Quiz.objects.create(student=student, subject=note.subject)
    Question.objects.bulk_create([
        Question(
            quiz=quiz,
            question_text=item["question"],
            topic=item["topic"],
            option_a=item["options"][0],
            option_b=item["options"][1],
            option_c=item["options"][2],
            option_d=item["options"][3],
            correct_answer=item["answer"],
        )
        for item in questions_data
    ])

    if len(questions_data) < question_count:
        dj_messages.warning(
            request,
            f"This note supported {len(questions_data)} of your {question_count} requested questions.",
        )

    return redirect("take_quiz", quiz_id=quiz.id)


@login_required
def take_quiz(request, quiz_id):
    """Renders the quiz form with questions and options."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    quiz = get_object_or_404(Quiz, id=quiz_id, student=student)
    questions = Question.objects.filter(quiz=quiz)

    return render(request, "take_quiz.html", {
        "quiz": quiz,
        "questions": questions,
    })


@login_required
@require_POST
def submit_quiz(request, quiz_id):
    """Evaluates student quiz answers and renders results."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    quiz = get_object_or_404(Quiz, id=quiz_id, student=student)

    eval_result = evaluate_quiz_submission(quiz, request.POST)
    record_study_day(student)

    history_scores = list(
        Quiz.objects.filter(student=student).order_by("date").values_list("score", flat=True)
    )

    questions_review = Question.objects.filter(quiz=quiz).select_related("answer_record")

    return render(request, "quiz_result.html", {
        "quiz": quiz,
        "questions": questions_review,
        "correct_count": eval_result["correct_count"],
        "wrong_count": eval_result["wrong_count"],
        "total": eval_result["total"],
        "history_scores": history_scores,
    })


@login_required
def view_quiz_result(request, quiz_id):
    """Displays answers and score for a previously completed quiz."""
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    quiz = get_object_or_404(Quiz, id=quiz_id, student=student)

    questions = Question.objects.filter(quiz=quiz).select_related("answer_record")
    total = questions.count()
    correct_count = sum(
        1 for q in questions
        if hasattr(q, "answer_record") and q.answer_record.is_correct
    )
    wrong_count = total - correct_count

    history_scores = list(
        Quiz.objects.filter(student=student).order_by("date").values_list("score", flat=True)
    )

    return render(request, "quiz_result.html", {
        "quiz": quiz,
        "questions": questions,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total": total,
        "history_scores": history_scores,
    })
