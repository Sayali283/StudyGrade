"""
URL Routing for StudyGrade REST API (v1).
"""
from django.urls import path
from . import views

urlpatterns = [
    path("health/", views.health_check, name="api_health"),
    path("streak/", views.get_streak_api, name="api_streak"),
    path("analytics/", views.get_analytics_api, name="api_analytics"),
    path("pomodoro/complete/", views.record_focus_block_api, name="api_pomodoro_complete"),
    path("notes/", views.list_student_notes_api, name="api_notes_list"),
    path("notes/<int:note_id>/flashcards/", views.get_flashcards_api, name="api_flashcards_get"),
]
