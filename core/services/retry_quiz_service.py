"""
Intelligent Retry Quiz Service:
Provides targeted practice workflows connected to the Mistake Notebook and weak topics.
Supports:
1. Quick Retry (3-5 questions)
2. Mistake Practice (unresolved mistakes)
3. Topic Mastery (in-depth assessment of selected topic)
"""
import re
import json
import random
import logging
from django.conf import settings
from google import genai
from decouple import config

from core.models import Student, Notes, Quiz, Question, QuestionAnswer, MistakeRecord
from core.services.document_service import extract_document_text
from core.services.quiz_service import _validate_and_sanitize_question

logger = logging.getLogger(__name__)


def generate_retry_quiz(
    student: Student,
    mode: str = "quick",  # 'quick', 'mistakes', 'topic'
    topic: str = "",
    subject: str = "",
    question_count: int = 5,
    mistake_ids: list[int] | None = None,
) -> Quiz | None:
    """
    Creates a Quiz with questions generated for weak spots and unresolved mistakes.
    Validates all questions and reuses the core Quiz data model.
    """
    if mode == "quick":
        question_count = max(3, min(question_count or 5, 5))
    elif mode == "mistakes":
        question_count = max(3, min(question_count or 5, 10))
    elif mode == "topic":
        question_count = max(5, min(question_count or 10, 20))
    else:
        question_count = 5

    # Gather mistake context
    mistake_qs = MistakeRecord.objects.filter(student=student, is_in_revision=True)
    if mistake_ids:
        mistake_qs = mistake_qs.filter(id__in=mistake_ids)
    elif topic:
        mistake_qs = mistake_qs.filter(topic__iexact=topic)
    elif subject:
        mistake_qs = mistake_qs.filter(subject__iexact=subject)
    else:
        # Prioritize unresolved mistakes
        mistake_qs = mistake_qs.order_by("-mistake_count", "-last_missed_at")

    selected_mistakes = list(mistake_qs[:question_count])

    quiz_subject = subject or (selected_mistakes[0].subject if selected_mistakes else "Targeted Practice")
    quiz_topic = topic or (selected_mistakes[0].topic if selected_mistakes else quiz_subject)

    # Find student's notes for grounding if available
    matching_note = Notes.objects.filter(
        student=student,
        subject__icontains=quiz_subject,
    ).first() or Notes.objects.filter(student=student).first()

    note_text = extract_document_text(matching_note.file) if matching_note and matching_note.file else ""

    # Generate or assemble retry questions
    questions_data = _generate_retry_questions(
        student=student,
        mistakes=selected_mistakes,
        note_text=note_text,
        quiz_subject=quiz_subject,
        quiz_topic=quiz_topic,
        question_count=question_count,
        mode=mode,
    )

    if not questions_data:
        return None

    # Create standard Quiz and Question objects
    quiz = Quiz.objects.create(
        student=student,
        subject=f"Retry Quiz ({mode.title()}): {quiz_topic}",
    )

    questions_to_create = []
    for item in questions_data:
        questions_to_create.append(Question(
            quiz=quiz,
            question_text=item["question"],
            topic=item.get("topic") or quiz_topic,
            option_a=item["options"][0],
            option_b=item["options"][1],
            option_c=item["options"][2],
            option_d=item["options"][3],
            correct_answer=item["answer"],
            explanation=item.get("explanation", ""),
            difficulty=item.get("difficulty", "medium"),
            source_reference=item.get("source_reference", ""),
        ))

    Question.objects.bulk_create(questions_to_create)
    return quiz


def _generate_retry_questions(
    student: Student,
    mistakes: list[MistakeRecord],
    note_text: str,
    quiz_subject: str,
    quiz_topic: str,
    question_count: int,
    mode: str,
) -> list[dict]:
    """
    Synthesizes alternative questions testing the same underlying concept.
    Falls back to validated questions or variations of missed questions.
    """
    questions_data = []
    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)

    # Contextualize previous mistakes
    mistakes_context = []
    for m in mistakes:
        mistakes_context.append(
            f"Concept/Topic: {m.topic}\n"
            f"Original Question: {m.question_text}\n"
            f"Student Selected: {m.selected_answer}\n"
            f"Correct Principle: {m.correct_answer}\n"
            f"Explanation: {m.explanation}\n"
        )
    mistakes_summary = "\n---\n".join(mistakes_context) if mistakes_context else f"Focus Topic: {quiz_topic}"

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
You are an intelligent educational retry engine.
Generate exactly {question_count} MULTIPLE CHOICE practice questions for a student who previously struggled with these concepts.

RULES:
1. Do NOT repeat the exact identical questions word-for-word. Generate DIFFERENT questions that test the SAME underlying principle or correct concept.
2. Provide plausible distractors based on common student misconceptions.
3. Base facts strictly on the notes or the verified correct principles below.
4. Return ONLY a valid JSON array of objects:
[
  {{
    "question": "Clear problem statement",
    "topic": "{quiz_topic}",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Option A",
    "explanation": "Why Option A is correct and why other options are false",
    "difficulty": "medium"
  }}
]

<STUDENT_MISTAKES_TO_REMEDIATE>
{mistakes_summary}
</STUDENT_MISTAKES_TO_REMEDIATE>

<STUDY_NOTES>
{note_text[:12000]}
</STUDY_NOTES>
"""
            resp = client.models.generate_content(
                model=getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
                contents=prompt,
            )
            if resp and resp.text:
                json_match = re.search(r"\[[\s\S]*\]", resp.text)
                if json_match:
                    raw_items = json.loads(json_match.group(0))
                    for item in raw_items:
                        sanitized = _validate_and_sanitize_question(item, quiz_topic)
                        if sanitized:
                            questions_data.append(sanitized)
                            if len(questions_data) >= question_count:
                                break
        except Exception as err:
            logger.warning("Gemini retry quiz generation error: %s", err)

    # Deterministic fallback: Use variation of existing mistakes or validated questions
    if len(questions_data) < question_count:
        for m in mistakes:
            if len(questions_data) >= question_count:
                break
            # Create a clean practice question testing the correct principle
            target_answer = m.correct_answer
            distractor_1 = m.selected_answer if m.selected_answer and m.selected_answer != target_answer else "Incorrect assumption"
            distractor_2 = f"Opposite mechanism of {m.topic}"
            distractor_3 = "Unrelated alternative factor"

            options = [target_answer, distractor_1, distractor_2, distractor_3]
            random.shuffle(options)

            variation_q = {
                "question": f"Review Practice on {m.topic}: Which statement accurately represents '{target_answer}'?",
                "topic": m.topic,
                "options": options,
                "answer": target_answer,
                "explanation": m.explanation or f"In {m.topic}, the verified principle is: {target_answer}.",
                "difficulty": "medium",
                "source_reference": f"Mistake review: {m.topic}",
            }
            questions_data.append(variation_q)

    # If still need more questions and notes exist, use document fallback
    if len(questions_data) < question_count and note_text:
        from core.services.quiz_service import _fallback_quiz_questions
        remaining = question_count - len(questions_data)
        fallback_qs = _fallback_quiz_questions(note_text, remaining, quiz_topic)
        questions_data.extend(fallback_qs)

    return questions_data[:question_count]
