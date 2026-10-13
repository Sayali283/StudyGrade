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
]

