"""
Utility functions for text formatting, dates, and response helpers.
"""
from django.utils import timezone


def format_duration(seconds: int) -> str:
    """Formats an integer number of seconds into MM:SS format."""
    minutes = seconds // 60
    rem_seconds = seconds % 60
    return f"{minutes:02d}:{rem_seconds:02d}"


def truncate_text(text: str, max_chars: int = 100) -> str:
    """Truncates text cleanly at word boundaries."""
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars].rsplit(" ", 1)[0]
    return f"{truncated}..."
