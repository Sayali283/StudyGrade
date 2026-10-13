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

    # Notes
    path('student/notes/', views.student_notes, name='student_notes'),
    path('student/notes/view/<int:note_id>/', views.view_note, name='view_note'),
    path('student/notes/delete/<int:note_id>/', views.delete_note, name='delete_note'),
    path('delete-note/<int:note_id>/', views.delete_note),

    # Quizzes
    path('student/quiz/', views.quiz_home, name='quiz_home'),
    path('student/quiz/generate/<int:note_id>/', views.generate_quiz, name='generate_quiz'),
    path('student/quiz/take/<int:quiz_id>/', views.take_quiz, name='take_quiz'),
    path('student/quiz/submit/<int:quiz_id>/', views.submit_quiz, name='submit_quiz'),
    path('student/quiz/result/<int:quiz_id>/', views.view_quiz_result, name='view_quiz_result'),
    path('student/quiz/question/<int:question_id>/report/', views.report_question, name='report_question'),

    # Mistake Notebook (PART 1)
    path('student/mistakes/', views.mistake_notebook, name='mistake_notebook'),
    path('student/mistakes/<int:mistake_id>/', views.mistake_detail, name='mistake_detail'),
    path('student/mistakes/<int:mistake_id>/toggle/', views.toggle_mistake_revision, name='toggle_mistake_revision'),
    path('student/mistakes/<int:mistake_id>/retry/', views.quick_retry_mistake, name='quick_retry_mistake'),

    # Intelligent Retry Quiz (PART 2)
    path('student/quiz/retry/', views.retry_quiz_setup, name='retry_quiz_setup'),

    # Spaced Repetition & Daily Revision (PART 3)
    path('student/revision/', views.revision_today, name='revision_today'),
    path('student/revision/session/', views.start_revision_session, name='start_revision_session'),
    path('student/revision/<int:review_id>/feedback/', views.submit_review_feedback, name='submit_review_feedback'),
    path('student/revision/add/', views.add_concept_to_revision, name='add_concept_to_revision'),

    # Flashcards
    path('student/flashcards/', views.flashcard_home, name='flashcard_home'),
    path('student/flashcards/generate/<int:note_id>/', views.generate_flashcards, name='generate_flashcards'),
    path('student/flashcards/<int:note_id>/', views.study_flashcards, name='study_flashcards'),
    path('student/flashcards/<int:note_id>/complete/', views.complete_flashcard_session, name='complete_flashcard_session'),

    # Visual Flowcharts & Mindmaps (PART 4)
    path('student/notes/<int:note_id>/flowchart/', views.note_flowchart, name='note_flowchart'),
    path('student/diagram/<int:chart_id>/save/', views.save_flowchart_source, name='save_flowchart_source'),
    path('student/diagram/<int:chart_id>/restore/<int:version_id>/', views.restore_flowchart_version, name='restore_flowchart_version'),
    path('student/diagram/<int:chart_id>/duplicate/', views.duplicate_flowchart, name='duplicate_flowchart'),
    path('student/diagram/<int:chart_id>/test/', views.diagram_test_me, name='diagram_test_me'),

    # Cornell Short Notes & Cheat Sheets (PART 5)
    path('student/notes/<int:note_id>/shortnotes/', views.note_shortnotes, name='note_shortnotes'),
    path('student/notes/<int:short_note_id>/edit/', views.save_shortnotes_edit, name='save_shortnotes_edit'),
    path('student/notes/<int:short_note_id>/restore/<int:version_id>/', views.restore_shortnotes_version, name='restore_shortnotes_version'),
    path('student/notes/<int:short_note_id>/cornell-review/', views.cornell_interactive_review, name='cornell_interactive_review'),
    path('student/notes/<int:short_note_id>/flashcards/', views.create_flashcards_from_cues, name='create_flashcards_from_cues'),
    path('student/notes/<int:short_note_id>/share/', views.share_shortnote_toggle, name='share_shortnote_toggle'),
    path('notes/shared/<str:share_token>/', views.public_shortnote_view, name='public_shortnote_view'),

    # Quiz Remediation
    path('student/quiz/<int:quiz_id>/remediation/', views.quiz_remediation, name='quiz_remediation'),
    path('student/remediation/<int:remediation_id>/resolve/', views.resolve_remediation, name='resolve_remediation'),

    # Progress & Analytics
    path("student/progress/", views.student_progress, name="student_progress"),
]
