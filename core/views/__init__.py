"""
View package for StudyGrade.
Modularized into:
- auth_views: home, login, logout, registration
- notes_views: note upload, secure streaming, deletion
- quiz_views: quiz center, generation, test-taking, review
- flashcard_views: decks, AI/heuristic cards, interactive studio
- pomodoro_views: timer studio, session streak updates
- dashboard_views: student & parent metrics, progress analytics
- study_suite_views: flowcharts, short notes, versions, interactive review, remediation
- mistake_views: mistake notebook, revision toggle, details
- retry_quiz_views: retry launcher and practice
- spaced_repetition_views: daily revision dashboard and session
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
from .study_suite_views import (
    note_flowchart,
    save_flowchart_source,
    restore_flowchart_version,
    duplicate_flowchart,
    diagram_test_me,
    note_shortnotes,
    save_shortnotes_edit,
    restore_shortnotes_version,
    cornell_interactive_review,
    create_flashcards_from_cues,
    share_shortnote_toggle,
    public_shortnote_view,
    quiz_remediation,
    resolve_remediation,
)
from .mistake_views import (
    mistake_notebook,
    mistake_detail,
    toggle_mistake_revision,
)
from .retry_quiz_views import (
    retry_quiz_setup,
    quick_retry_mistake,
)
from .spaced_repetition_views import (
    revision_today,
    start_revision_session,
    submit_review_feedback,
    add_concept_to_revision,
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
    "note_flowchart",
    "save_flowchart_source",
    "restore_flowchart_version",
    "duplicate_flowchart",
    "diagram_test_me",
    "note_shortnotes",
    "save_shortnotes_edit",
    "restore_shortnotes_version",
    "cornell_interactive_review",
    "create_flashcards_from_cues",
    "share_shortnote_toggle",
    "public_shortnote_view",
    "quiz_remediation",
    "resolve_remediation",
    "mistake_notebook",
    "mistake_detail",
    "toggle_mistake_revision",
    "retry_quiz_setup",
    "quick_retry_mistake",
    "revision_today",
    "start_revision_session",
    "submit_review_feedback",
    "add_concept_to_revision",
]
