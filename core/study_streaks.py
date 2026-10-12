"""
Backward-compatible proxy to core.services.streak_service.
"""
from core.services.streak_service import get_study_streak, record_study_day

__all__ = ["get_study_streak", "record_study_day"]