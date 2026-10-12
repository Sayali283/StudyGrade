"""
Quiz Service.
Handles AI-powered multiple-choice quiz generation, intelligent NLP fallback,
and quiz submission evaluation and scoring.
"""
import sys
import json
import random
import re as regex
from django.conf import settings
from google import genai

from core.models import Question, QuestionAnswer, Quiz


STOP_WORDS = {
    "about", "above", "after", "again", "against", "all", "and", "any", "are", "aren't",
    "because", "been", "before", "being", "below", "between", "both", "but", "by", "can't",
    "cannot", "could", "couldn't", "did", "didn't", "does", "doesn't", "doing", "don't",
    "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "into", "is",
    "isn't", "it", "it's", "its", "itself", "let's", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "off", "once", "only", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's",
    "should", "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their",
    "theirs", "them", "themselves", "then", "there", "there's", "these", "they", "they'd",
    "they'll", "they're", "they've", "this", "those", "through", "under", "until",
    "up", "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which", "while",
    "who", "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you",
    "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"
}


def generate_quiz_questions(text: str, question_count: int, default_topic: str) -> list[dict]:
    """
    Generates a list of multiple choice questions from study notes.
    Attempts Gemini AI generation first; falls back to document-wide NLP extraction if AI is unavailable.
    """
    questions_data = []

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    core_views = sys.modules.get("core.views")
    has_mock = bool(core_views and hasattr(core_views, "genai") and hasattr(core_views.genai, "Client"))

    if api_key or has_mock:
        try:
            prompt = f"""
Generate exactly {question_count} intelligent multiple-choice questions from the study notes.
Return ONLY a valid JSON array. Each item must use this format:
{{"question": "...", "topic": "short topic label", "options": ["A", "B", "C", "D"], "answer": "exactly one option"}}
Use only information stated in the notes. Make questions distinct, label their specific topic, and distribute them across the material.

NOTES:
{text}
"""
            genai_module = getattr(core_views, "genai", genai) if core_views else genai
            client = genai_module.Client(api_key=api_key)
            models_to_try = [
                getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
                "gemini-3.8-flash",
                "gemini-2.5-flash",
                "gemini-1.5-flash",
            ]
            response = None
            for model_name in models_to_try:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    if response and response.text:
                        break
                except Exception:
                    continue
            response_text = (response.text if response else "") or ""

            json_match = regex.search(r"\[[\s\S]*\]", response_text)
            if json_match:
                generated = json.loads(json_match.group(0))
                if isinstance(generated, list):
                    seen_questions = set()
                    for item in generated:
                        if not isinstance(item, dict):
                            continue
                        question = (item.get("question") or "").strip()
                        topic = (item.get("topic") or default_topic).strip()[:100] or default_topic
                        options = [o.strip() for o in item.get("options", []) if isinstance(o, str) and o.strip()]
                        answer = (item.get("answer") or "").strip()

                        if len(question) < 8 or len(set(o.casefold() for o in options)) < 4:
                            continue
                        options = options[:4]
                        if not any(o.casefold() == answer.casefold() for o in options):
                            continue

                        norm_q = question.casefold()
                        if norm_q in seen_questions:
                            continue
                        seen_questions.add(norm_q)

                        matching_answer = next(o for o in options if o.casefold() == answer.casefold())
                        questions_data.append({
                            "question": question,
                            "topic": topic,
                            "options": options,
                            "answer": matching_answer,
                        })
                        if len(questions_data) == question_count:
                            break
        except Exception as error:
            print(f"[QuizService] Gemini generation skipped/failed: {error}")

    # 2. Intelligent NLP Fallback if remaining questions needed
    if len(questions_data) < question_count:
        remaining = question_count - len(questions_data)
        fallback = _fallback_quiz_questions(
            text,
            remaining,
            default_topic,
            excluded_questions={item["question"].casefold() for item in questions_data},
        )
        questions_data.extend(fallback)

    return questions_data


def _fallback_quiz_questions(text: str, question_count: int, default_topic: str, excluded_questions: set = None) -> list[dict]:
    """Generates MCQs using document-wide terminology sampling and cloze-deletion."""
    excluded_questions = excluded_questions or set()
    questions_data = []
    seen_questions = set(excluded_questions)

    all_doc_words = regex.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text)
    doc_keywords = list(dict.fromkeys(
        w.capitalize() for w in all_doc_words
        if len(w) > 3 and w.isalpha() and w.lower() not in STOP_WORDS
    ))
    if len(doc_keywords) < 4:
        doc_keywords += ["Factor", "Concept", "Process", "System", "Method", "Variable"]

    sentences = [
        regex.sub(r"\s+", " ", s).strip(" \t-•")
        for s in regex.split(r"(?<=[.!?])\s+|\n+", text)
    ]
    candidate_sentences = [
        s for s in sentences
        if len(s.split()) >= 6 and len(s) >= 35
    ]

    for sentence in candidate_sentences:
        words = regex.findall(r"\b[A-Za-z][A-Za-z'-]*\b", sentence)
        keywords = [
            w for w in words
            if len(w) > 3 and w.isalpha() and w.lower() not in STOP_WORDS
        ]
        if not keywords:
            continue

        answer_word = random.choice(keywords)
        answer = answer_word.capitalize()
        question = regex.sub(
            rf"\b{regex.escape(answer_word)}\b",
            "_____",
            sentence,
            count=1,
            flags=regex.IGNORECASE,
        )
        norm_q = question.casefold()
        if norm_q in seen_questions:
            continue

        available_distractors = [
            kw for kw in doc_keywords
            if kw.casefold() != answer.casefold()
        ]
        if len(available_distractors) < 3:
            available_distractors += ["Theory", "Hypothesis", "Mechanism", "Observation"]

        chosen_distractors = random.sample(available_distractors, 3)
        options = chosen_distractors + [answer]
        random.shuffle(options)

        questions_data.append({
            "question": question,
            "topic": default_topic,
            "options": options,
            "answer": answer,
        })
        seen_questions.add(norm_q)
        if len(questions_data) >= question_count:
            break

    return questions_data


def evaluate_quiz_submission(quiz: Quiz, post_data: dict) -> dict:
    """
    Evaluates submitted answers for a quiz.
    Updates QuestionAnswer models and calculates total score percentage.
    """
    questions = Question.objects.filter(quiz=quiz)
    total = questions.count()
    correct_count = 0
    wrong_count = 0

    for q in questions:
        raw_user_answer = post_data.get(str(q.id), "")
        selected_answer = raw_user_answer.strip() if isinstance(raw_user_answer, str) else ""

        is_correct = bool(
            selected_answer
            and selected_answer.lower() == q.correct_answer.strip().lower()
        )

        if is_correct:
            correct_count += 1
        else:
            wrong_count += 1

        QuestionAnswer.objects.update_or_create(
            question=q,
            defaults={
                "selected_answer": selected_answer,
                "is_correct": is_correct,
            },
        )

    score_percentage = round((correct_count / total) * 100, 2) if total else 0.0
    quiz.score = score_percentage
    quiz.save(update_fields=["score"])

    return {
        "score": score_percentage,
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "total": total,
    }
