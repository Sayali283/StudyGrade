import json

from google import genai

from django.conf import settings
from django.db import transaction
from django.db.models import Count

from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages as dj_messages
from django.utils import timezone
from django.http import JsonResponse

from .models import Student, Parent, Notes, Quiz, Question, QuestionAnswer, Flashcard, StudyDay
from .forms import NotesForm
from .study_streaks import get_study_streak, record_study_day
from .topic_analytics import get_recommended_topic, get_topic_performance

from PyPDF2 import PdfReader

import random
import re as regex

STUDY_THOUGHTS = [
    "Small, focused steps add up to remarkable progress.",
    "You do not have to finish everything. Just begin the next thing.",
    "One quiet, focused session is a promise kept to your future self.",
    "Progress grows when you return to the work, one day at a time.",
    "Curiosity is a good reason to keep going.",
    "Give this moment your attention. The next step can wait.",
    "Every difficult idea gets easier with patient practice.",
]


def daily_study_thought():
    return STUDY_THOUGHTS[timezone.localdate().toordinal() % len(STUDY_THOUGHTS)]


# ---------- HOME ----------
def home(request):

    return render(request, "home.html")


# ---------- STUDENT SIGNUP ----------
def student_signup(request):

    if request.method == "POST":

        try:

            name = request.POST.get("name")
            email = request.POST.get("email")
            password = request.POST.get("password")
            class_semester = request.POST.get("class_semester")

            if not name or not email or not password or not class_semester:

                return render(request, "signup_student.html", {
                    "error": "All fields are required"
                })

            if User.objects.filter(username=email).exists():

                return render(request, "signup_student.html", {
                    "error": "Email already exists"
                })

            user = User.objects.create_user(
                username=email,
                first_name=name,
                email=email,
                password=password
            )

            Student.objects.create(
                user=user,
                class_semester=class_semester
            )

            login(request, user)

            return redirect("student_dashboard")

        except Exception as e:

            return render(request, "signup_student.html", {
                "error": str(e)
            })

    return render(request, "signup_student.html")


# ---------- PARENT SIGNUP ----------
def parent_signup(request):

    if request.method == "POST":

        try:

            name = request.POST.get("name")
            email = request.POST.get("email")
            password = request.POST.get("password")
            student_email = request.POST.get("student_email")

            if User.objects.filter(username=email).exists():

                dj_messages.error(
                    request,
                    "Email already registered"
                )

                return redirect("parent_signup")

            try:

                student = Student.objects.get(
                    user__email=student_email
                )

            except Student.DoesNotExist:

                dj_messages.error(
                    request,
                    "Student email not found"
                )

                return redirect("parent_signup")

            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                password=password
            )

            Parent.objects.create(
                user=user,
                student=student
            )

            dj_messages.success(
                request,
                "Parent account created successfully"
            )

            return redirect("login")

        except Exception as e:

            dj_messages.error(
                request,
                str(e)
            )

            return redirect("parent_signup")

    return render(request, "signup_parent.html")


# ---------- LOGIN ----------
def user_login(request):

    if request.method == "POST":

        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if user is not None:

            login(request, user)

            if hasattr(user, "student"):
                return redirect("student_dashboard")

            elif hasattr(user, "parent"):
                return redirect("parent_dashboard")

            else:
                return redirect("home")

        else:

            dj_messages.error(
                request,
                "Invalid email or password"
            )

    return render(request, "login.html")


# ---------- LOGOUT ----------
def user_logout(request):

    logout(request)

    return redirect("home")


# ---------- STUDENT DASHBOARD ----------
@login_required
def student_dashboard(request):

    if not hasattr(request.user, "student"):

        return redirect("login")

    student = request.user.student

    total_notes = Notes.objects.filter(
        student=student
    ).count()

    quizzes = Quiz.objects.filter(
        student=student
    )

    total_quizzes = quizzes.count()

    scores = [
        q.score
        for q in quizzes
        if q.score is not None
    ]

    avg_score = (
        round(sum(scores) / len(scores), 2)
        if scores else 0
    )

    last_quiz = quizzes.order_by("-date").first()

    last_score = (
        last_quiz.score
        if last_quiz else 0
    )

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
def pomodoro_timer(request):
    if not hasattr(request.user, "student"):
        return redirect("login")
    return render(request, "pomodoro.html", {"daily_thought": daily_study_thought()})


@login_required
@require_POST
def complete_pomodoro_session(request):
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    record_study_day(student)
    return JsonResponse({
        "current_streak": get_study_streak(student),
        "message": "Focus session complete. Your study streak has been updated.",
    })


# ---------- STUDENT NOTES ----------
@login_required
def student_notes(request):

    if not hasattr(request.user, "student"):

        return redirect("login")

    notes = Notes.objects.filter(
        student=request.user.student
    )

    if request.method == "POST":

        form = NotesForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():

            note = form.save(commit=False)

            note.student = request.user.student

            note.save()

            dj_messages.success(
                request,
                "Note uploaded successfully"
            )

            return redirect("student_notes")

    else:

        form = NotesForm()

    return render(request, "student_notes.html", {
        "notes": notes,
        "form": form
    })


# ---------- DELETE NOTE ----------
@login_required
def delete_note(request, note_id):

    note = get_object_or_404(
        Notes,
        id=note_id
    )

    if note.student == request.user.student:

        if note.file:
            note.file.delete()

        note.delete()

        dj_messages.success(
            request,
            "Note deleted successfully"
        )

    return redirect("student_notes")


def _extract_note_text(note):
    file_path = note.file.path

    if file_path.lower().endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(
            page.extract_text() or ""
            for page in reader.pages
        )

    if file_path.lower().endswith(".txt"):
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()

    raise ValueError("Only PDF and TXT notes can be used for flashcards.")


def _fallback_flashcards(text):
    candidates = []
    seen = set()

    for index, sentence in enumerate(regex.split(r"(?<=[.!?])\s+|\n+", text)):
        sentence = regex.sub(r"\s+", " ", sentence).strip(" \t-•")
        words = sentence.split()
        normalized = sentence.casefold()

        if len(words) < 7 or len(sentence) < 45 or normalized in seen:
            continue

        seen.add(normalized)
        score = min(len(words), 30)
        if regex.search(r"\b(is defined as|refers to|means|consists of|is|are)\b", sentence, regex.IGNORECASE):
            score += 8
        if regex.search(r"\b(because|therefore|important|process|function|causes|results)\b", sentence, regex.IGNORECASE):
            score += 5
        if regex.search(r"\d", sentence):
            score += 2

        candidates.append((score, index, words, sentence))

    selected = sorted(candidates, key=lambda item: (-item[0], item[1]))[:10]
    selected.sort(key=lambda item: item[1])

    return [
        {
            "front": f"Complete this key point: {' '.join(words[:max(3, len(words) // 3)])} ...",
            "back": sentence,
        }
        for _, _, words, sentence in selected
    ]


@login_required
def flashcard_home(request):
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    notes = Notes.objects.filter(student=student).annotate(
        flashcard_count=Count("flashcards")
    ).order_by("subject")

    return render(request, "flashcard_home.html", {"notes": notes})


@login_required
def study_flashcards(request, note_id):
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)
    cards = list(note.flashcards.all())
    flashcards_data = [
        {"front": card.front, "back": card.back}
        for card in cards
    ]

    return render(request, "flashcard_study.html", {
        "note": note,
        "cards": cards,
        "flashcards_data": flashcards_data,
    })


@login_required
@require_POST
def generate_flashcards(request, note_id):
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)

    try:
        text = _extract_note_text(note).strip()
    except Exception:
        dj_messages.error(request, "We could not read that file. Please upload a text-based PDF or TXT note.")
        return redirect("flashcard_home")

    if len(text) < 80:
        dj_messages.error(request, "This note does not contain enough readable text to make flashcards.")
        return redirect("flashcard_home")

    prompt = f"""
Create 6 to 10 useful study flashcards from these notes about {note.subject}.
Focus on the most important concepts, definitions, processes, and cause-and-effect relationships.
Each front must ask one clear recall question. Each back must give a concise answer using only the notes.
Avoid duplicate cards and minor details. Return ONLY a valid JSON array in this format:
[{{"front": "Question", "back": "Answer"}}]

NOTES:
{text[:18000]}
"""

    cards_data = []
    try:
        response = genai.Client(api_key=settings.GEMINI_API_KEY).models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        response_text = (response.text or "").strip()
        json_match = regex.search(r"\[[\s\S]*\]", response_text)
        if json_match:
            generated = json.loads(json_match.group(0))
            if isinstance(generated, list):
                cards_data = [
                    {"front": item.get("front", "").strip(), "back": item.get("back", "").strip()}
                    for item in generated
                    if isinstance(item, dict)
                    and isinstance(item.get("front"), str)
                    and isinstance(item.get("back"), str)
                    and item.get("front", "").strip()
                    and item.get("back", "").strip()
                ]
    except Exception:
        cards_data = []

    if not cards_data:
        cards_data = _fallback_flashcards(text)

    if not cards_data:
        dj_messages.error(request, "We could not find enough key points in this note to make flashcards.")
        return redirect("flashcard_home")

    with transaction.atomic():
        note.flashcards.all().delete()
        Flashcard.objects.bulk_create([
            Flashcard(note=note, front=card["front"], back=card["back"])
            for card in cards_data
        ])

    dj_messages.success(request, f"Created {len(cards_data)} flashcards for {note.subject}.")
    return redirect("study_flashcards", note_id=note.id)


@login_required
@require_POST
def complete_flashcard_session(request, note_id):
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    note = get_object_or_404(Notes, id=note_id, student=student)
    if not note.flashcards.exists():
        dj_messages.error(request, "Generate flashcards before completing a study session.")
        return redirect("flashcard_home")

    record_study_day(student)
    streak = get_study_streak(student)
    dj_messages.success(
        request,
        f"Study session complete. Your current streak is {streak} day{'' if streak == 1 else 's'}.",
    )
    return redirect("study_flashcards", note_id=note.id)


# ---------- QUIZ HOME ----------
@login_required
def quiz_home(request):

    student = request.user.student

    notes = Notes.objects.filter(
        student=student
    )

    quizzes = Quiz.objects.filter(
        student=student
    ).order_by("-date")

    return render(request, "quiz_home.html", {
        "notes": notes,
        "quizzes": quizzes
    })


# ---------- GENERATE QUIZ ----------
@login_required
@require_POST
def generate_quiz(request, note_id):
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return redirect("login")

    try:
        question_count = int(request.POST.get("question_count", ""))
    except (TypeError, ValueError):
        question_count = 0

    if question_count not in {5, 10, 20, 30}:
        dj_messages.error(request, "Choose 5, 10, 20, or 30 questions.")
        return redirect("quiz_home")

    note = get_object_or_404(Notes, id=note_id, student=student)
    file_path = note.file.path

    try:
        if file_path.lower().endswith(".txt"):
            with open(file_path, "r", encoding="utf-8") as file:
                text = file.read()
        elif file_path.lower().endswith(".pdf"):
            reader = PdfReader(file_path)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            dj_messages.error(request, "Only PDF and TXT notes can be used to generate quizzes.")
            return redirect("quiz_home")
    except Exception:
        dj_messages.error(request, "We could not read that file. Please upload a text-based PDF or TXT note.")
        return redirect("quiz_home")

    text = text.strip()[:18000]
    if len(text.split()) < 12:
        dj_messages.error(request, "This note does not contain enough readable text to generate a quiz.")
        return redirect("quiz_home")

    questions_data = []
    try:
        prompt = f"""
Generate exactly {question_count} intelligent multiple-choice questions from the study notes.
Return ONLY a valid JSON array. Each item must use this format:
{{"question": "...", "topic": "short topic label", "options": ["A", "B", "C", "D"], "answer": "exactly one option"}}
Use only information stated in the notes. Make questions distinct, label their specific topic, and distribute them across the material.

NOTES:
{text}
"""
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        response_text = (response.text or "").strip()
        json_match = regex.search(r"\[[\s\S]*\]", response_text)
        if not json_match:
            raise ValueError("The quiz generator did not return a JSON question list.")

        generated = json.loads(json_match.group(0))
        if not isinstance(generated, list):
            raise ValueError("The quiz generator returned an invalid question list.")

        seen_questions = set()
        for item in generated:
            if not isinstance(item, dict):
                continue
            question = item.get("question")
            topic = item.get("topic", note.subject)
            options = item.get("options")
            answer = item.get("answer")
            if not isinstance(question, str) or not isinstance(options, list) or not isinstance(answer, str):
                continue

            question = question.strip()
            topic = topic.strip()[:100] if isinstance(topic, str) and topic.strip() else note.subject
            options = [option.strip() for option in options if isinstance(option, str) and option.strip()]
            if len(question) < 8 or len(set(option.casefold() for option in options)) < 4:
                continue
            options = options[:4]
            if not any(option.casefold() == answer.strip().casefold() for option in options):
                continue

            normalized_question = question.casefold()
            if normalized_question in seen_questions:
                continue
            seen_questions.add(normalized_question)
            questions_data.append({
                "question": question,
                "topic": topic,
                "options": options,
                "answer": next(option for option in options if option.casefold() == answer.strip().casefold()),
            })
            if len(questions_data) == question_count:
                break
    except Exception as error:
        print("AI FAILED:", str(error))

    if len(questions_data) < question_count:
        remaining_count = question_count - len(questions_data)
        fallback_questions = _fallback_quiz_questions(
            text,
            remaining_count,
            note.subject,
            {item["question"].casefold() for item in questions_data},
        )
        questions_data.extend(fallback_questions)

    if not questions_data:
        dj_messages.error(request, "Could not generate quiz questions from this note.")
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


def _fallback_quiz_questions(text, question_count, default_topic, excluded_questions=None):
    excluded_questions = excluded_questions or set()
    questions_data = []
    seen_questions = set(excluded_questions)

    for sentence in regex.split(r"(?<=[.!?])\s+|\n+", text):
        sentence = regex.sub(r"\s+", " ", sentence).strip(" \t-•")
        words = regex.findall(r"\b[A-Za-z][A-Za-z'-]*\b", sentence)
        keywords = list(dict.fromkeys(word for word in words if len(word) > 4 and word.isalpha()))
        if len(keywords) < 4:
            continue

        answer = random.choice(keywords)
        question = regex.sub(
            rf"\b{regex.escape(answer)}\b",
            "_____",
            sentence,
            count=1,
            flags=regex.IGNORECASE,
        )
        normalized_question = question.casefold()
        wrong_answers = [word for word in keywords if word.casefold() != answer.casefold()]
        if normalized_question in seen_questions or len(wrong_answers) < 3:
            continue

        options = random.sample(wrong_answers, 3) + [answer]
        random.shuffle(options)
        questions_data.append({
            "question": question,
            "topic": default_topic,
            "options": options,
            "answer": answer,
        })
        seen_questions.add(normalized_question)
        if len(questions_data) >= question_count:
            break

    return questions_data
# ---------- TAKE QUIZ ----------
@login_required
def take_quiz(request, quiz_id):

    quiz = get_object_or_404(
        Quiz,
        id=quiz_id
    )

    questions = Question.objects.filter(
        quiz=quiz
    )

    return render(request, "take_quiz.html", {
        "quiz": quiz,
        "questions": questions
    })


# ---------- SUBMIT QUIZ ----------
@login_required
@require_POST
def submit_quiz(request, quiz_id):

    quiz = get_object_or_404(
        Quiz,
        id=quiz_id,
        student=request.user.student
    )

    questions = Question.objects.filter(
        quiz=quiz
    )

    score = 0

    correct_count = 0

    wrong_count = 0

    total = questions.count()

    for q in questions:

        user_answer = request.POST.get(str(q.id))
        selected_answer = user_answer.strip() if user_answer else ""

        if (
            selected_answer
            and selected_answer.lower()
            == q.correct_answer.strip().lower()
        ):

            score += 1

            correct_count += 1

            is_correct = True

        else:

            wrong_count += 1

            is_correct = False

        QuestionAnswer.objects.update_or_create(
            question=q,
            defaults={
                "selected_answer": selected_answer,
                "is_correct": is_correct,
            },
        )

    quiz.score = (
        round((score / total) * 100, 2)
        if total else 0
    )

    quiz.save()
    record_study_day(request.user.student)

    history_scores = list(

        Quiz.objects.filter(
            student=request.user.student
        ).order_by("date")
        .values_list("score", flat=True)

    )

    return render(request, "quiz_result.html", {
        "quiz": quiz,
        "questions": questions,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total": total,
        "history_scores": history_scores
    })


# ---------- STUDENT PROGRESS ----------
@login_required
def student_progress(request):

    quizzes = Quiz.objects.filter(
        student=request.user.student
    ).order_by("date")

    total_quizzes = quizzes.count()

    scores = [
        q.score
        for q in quizzes
        if q.score is not None
    ]

    average_score = (
        round(sum(scores) / len(scores), 2)
        if scores else 0
    )

    best_score = max(scores) if scores else 0

    worst_score = min(scores) if scores else 0

    topic_performance = get_topic_performance(request.user.student)
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
            {"topic": topic["topic"], "accuracy": topic["accuracy"]}
            for topic in topic_performance
        ],
    })


# ---------- PARENT DASHBOARD ----------
@login_required
def parent_dashboard(request):

    if not hasattr(request.user, "parent"):

        return redirect("login")

    student = request.user.parent.student

    quizzes = Quiz.objects.filter(
        student=student
    ).order_by("date")

    scores = list(
        quizzes.values_list("score", flat=True)
    )

    total_quizzes = quizzes.count()

    average_score = (
        round(sum(scores) / total_quizzes, 2)
        if total_quizzes else 0
    )

    best_score = max(scores) if scores else 0

    worst_score = min(scores) if scores else 0

    return render(request, "parent_dashboard.html", {
        "student": student,
        "quizzes": quizzes,
        "scores": scores,
        "total_quizzes": total_quizzes,
        "average_score": average_score,
        "best_score": best_score,
        "worst_score": worst_score,
        "current_streak": get_study_streak(student),
        "last_study_day": StudyDay.objects.filter(student=student).first(),
    })