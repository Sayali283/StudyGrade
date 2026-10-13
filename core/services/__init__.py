"""
Service layer package for StudyGrade.
Encapsulates all domain and business logic away from HTTP views and database models.
"""
from .document_service import (
    extract_document_text,
    validate_document_file,
    DocumentExtractionError,
)
from .quiz_service import generate_quiz_questions, evaluate_quiz_submission
from .flashcard_service import generate_flashcard_items
from .streak_service import get_study_streak, record_study_day
from .analytics_service import get_topic_performance, get_recommended_topic
from .study_suite_service import (
    generate_flowchart_for_note,
    generate_shortnotes_for_note,
    generate_quiz_remediation,
    validate_mermaid_syntax,
    generate_diagram_quiz,
    create_flashcards_from_shortnote,
    save_shortnote_version,
)
from .mistake_service import (
    record_quiz_mistakes,
    get_student_mistakes,
    remove_mistake_from_revision,
    restore_mistake_to_revision,
    log_mistake_review,
)
from .retry_quiz_service import generate_retry_quiz
from .spaced_repetition_service import (
    schedule_mistake_review,
    schedule_concept_review,
    process_review_attempt,
    get_revision_today_summary,
)

__all__ = [
    "extract_document_text",
    "validate_document_file",
    "DocumentExtractionError",
    "generate_quiz_questions",
    "evaluate_quiz_submission",
    "generate_flashcard_items",
    "get_study_streak",
    "record_study_day",
    "get_topic_performance",
    "get_recommended_topic",
    "generate_flowchart_for_note",
    "generate_shortnotes_for_note",
    "generate_quiz_remediation",
    "validate_mermaid_syntax",
    "generate_diagram_quiz",
    "create_flashcards_from_shortnote",
    "save_shortnote_version",
    "record_quiz_mistakes",
    "get_student_mistakes",
    "remove_mistake_from_revision",
    "restore_mistake_to_revision",
    "log_mistake_review",
    "generate_retry_quiz",
    "schedule_mistake_review",
    "schedule_concept_review",
    "process_review_attempt",
    "get_revision_today_summary",
]
