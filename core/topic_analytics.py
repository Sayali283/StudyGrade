"""
Backward-compatible proxy to core.services.analytics_service.
"""
from core.services.analytics_service import get_topic_performance, get_recommended_topic

__all__ = ["get_topic_performance", "get_recommended_topic"]