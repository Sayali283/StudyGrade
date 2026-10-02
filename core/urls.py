from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    path('signup/student/', views.student_signup, name='student_signup'),
    path('signup/parent/', views.parent_signup, name='parent_signup'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),

    path('student/dashboard/', views.student_dashboard, name='student_dashboard'),
    path('student/pomodoro/', views.pomodoro_timer, name='pomodoro_timer'),
    path('student/pomodoro/complete/', views.complete_pomodoro_session, name='complete_pomodoro_session'),
    path('parent/dashboard/', views.parent_dashboard, name='parent_dashboard'),

    path('student/notes/', views.student_notes, name='student_notes'),
    path('student/notes/delete/<int:note_id>/', views.delete_note, name='delete_note'),

    path('student/quiz/', views.quiz_home, name='quiz_home'),
    path('student/quiz/generate/<int:note_id>/', views.generate_quiz, name='generate_quiz'),
    path('student/quiz/take/<int:quiz_id>/', views.take_quiz, name='take_quiz'),
    path('student/quiz/submit/<int:quiz_id>/', views.submit_quiz, name='submit_quiz'),
    path('student/flashcards/', views.flashcard_home, name='flashcard_home'),
    path('student/flashcards/generate/<int:note_id>/', views.generate_flashcards, name='generate_flashcards'),
    path('student/flashcards/<int:note_id>/', views.study_flashcards, name='study_flashcards'),
    path('student/flashcards/<int:note_id>/complete/', views.complete_flashcard_session, name='complete_flashcard_session'),
    path("student/progress/", views.student_progress, name="student_progress"),
    path("parent/dashboard/", views.parent_dashboard, name="parent_dashboard"),

]
