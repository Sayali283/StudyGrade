"""
View package for StudyGrade.
Modularized into:
- auth_views: home, login, logout, registration
- notes_views: note upload, secure streaming, deletion
- quiz_views: quiz center, generation, test-taking, review
- flashcard_views: decks, AI/heuristic cards, interactive studio
- pomodoro_views: timer studio, session streak updates
- dashboard_views: student & parent metrics, progress analytics
"""
from google import genai

from .auth_views import (
    home,
    student_signup,
    parent_signup,
    user_login,
    user_logout,
)
from .notes_views import (
    student_notes,
    view_note,
    delete_note,
)
from .quiz_views import (
    quiz_home,
    generate_quiz,
    take_quiz,
    submit_quiz,
    view_quiz_result,
    report_question,
)
from .flashcard_views import (
    flashcard_home,
    generate_flashcards,
    study_flashcards,
    complete_flashcard_session,
)
from .pomodoro_views import (
    pomodoro_timer,
    complete_pomodoro_session,
)
from .dashboard_views import (
    student_dashboard,
    parent_dashboard,
    student_progress,
)

__all__ = [
    "home",
    "student_signup",
    "parent_signup",
    "user_login",
    "user_logout",
    "student_notes",
    "view_note",
    "delete_note",
    "quiz_home",
    "generate_quiz",
    "take_quiz",
    "submit_quiz",
    "view_quiz_result",
    "report_question",
    "flashcard_home",
    "generate_flashcards",
    "study_flashcards",
    "complete_flashcard_session",
    "pomodoro_timer",
    "complete_pomodoro_session",
    "student_dashboard",
    "parent_dashboard",
    "student_progress",
]

