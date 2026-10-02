import json
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Flashcard, Notes, Parent, Quiz, Question, QuestionAnswer, Student, StudyDay
from .study_streaks import get_study_streak, record_study_day
from .topic_analytics import get_recommended_topic, get_topic_performance


class FlashcardGenerationTests(TestCase):
	def setUp(self):
		self.media_directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.media_directory.cleanup)
		media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
		media_settings.enable()
		self.addCleanup(media_settings.disable)

		self.user = User.objects.create_user(
			username="student@example.com",
			email="student@example.com",
			password="test-password",
		)
		self.student = Student.objects.create(user=self.user, class_semester="BCA")
		self.note = Notes.objects.create(
			student=self.student,
			subject="Biology",
			file=SimpleUploadedFile(
				"biology.txt",
				b"Photosynthesis converts light energy into chemical energy. "
				b"Chlorophyll absorbs light in the leaves of plants.",
			),
		)
		self.client.force_login(self.user)

	@patch("core.views.genai.Client")
	def test_generates_persists_and_renders_flashcards(self, gemini_client):
		gemini_client.return_value.models.generate_content.return_value = SimpleNamespace(
			text=json.dumps([
				{
					"front": "What does photosynthesis convert?",
					"back": "It converts light energy into chemical energy.",
				},
			])
		)

		response = self.client.post(
			reverse("generate_flashcards", args=[self.note.id])
		)

		self.assertRedirects(
			response,
			reverse("study_flashcards", args=[self.note.id]),
			fetch_redirect_response=False,
		)
		self.assertEqual(Flashcard.objects.filter(note=self.note).count(), 1)

		study_response = self.client.get(
			reverse("study_flashcards", args=[self.note.id])
		)
		self.assertContains(study_response, "What does photosynthesis convert?")
		self.assertContains(study_response, "It converts light energy into chemical energy.")

	def test_student_cannot_generate_cards_from_another_students_note(self):
		other_user = User.objects.create_user(
			username="other@example.com",
			email="other@example.com",
			password="test-password",
		)
		other_student = Student.objects.create(
			user=other_user,
			class_semester="BCA",
		)
		other_note = Notes.objects.create(
			student=other_student,
			subject="Private notes",
			file=SimpleUploadedFile("private.txt", b"Private study material."),
		)

		response = self.client.post(
			reverse("generate_flashcards", args=[other_note.id])
		)

		self.assertEqual(response.status_code, 404)
		self.assertFalse(Flashcard.objects.filter(note=other_note).exists())


class StudyStreakTests(TestCase):
	def setUp(self):
		self.student_user = User.objects.create_user(
			username="streak-student@example.com",
			email="streak-student@example.com",
			password="test-password",
		)
		self.student = Student.objects.create(
			user=self.student_user,
			class_semester="BCA",
		)

	def test_streak_counts_consecutive_days_once(self):
		today = timezone.localdate()
		record_study_day(self.student, today)
		record_study_day(self.student, today)
		record_study_day(self.student, today - timedelta(days=1))
		record_study_day(self.student, today - timedelta(days=3))

		self.assertEqual(StudyDay.objects.filter(student=self.student).count(), 3)
		self.assertEqual(get_study_streak(self.student, today), 2)

	def test_streak_resets_after_two_missed_days(self):
		today = timezone.localdate()
		record_study_day(self.student, today - timedelta(days=2))

		self.assertEqual(get_study_streak(self.student, today), 0)

	def test_pomodoro_page_is_available_to_students(self):
		self.client.force_login(self.student_user)

		response = self.client.get(reverse("pomodoro_timer"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Pomodoro timer")
		self.assertContains(response, "25 min")

	def test_completed_pomodoro_records_one_study_day(self):
		self.client.force_login(self.student_user)

		first_response = self.client.post(reverse("complete_pomodoro_session"))
		second_response = self.client.post(reverse("complete_pomodoro_session"))

		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(first_response.json()["current_streak"], 1)
		self.assertEqual(second_response.json()["current_streak"], 1)
		self.assertEqual(StudyDay.objects.filter(student=self.student).count(), 1)

	def test_flashcard_completion_records_today_and_updates_student_dashboard(self):
		note = Notes.objects.create(
			student=self.student,
			subject="Biology",
			file=SimpleUploadedFile("biology.txt", b"Study notes."),
		)
		Flashcard.objects.create(
			note=note,
			front="What is biology?",
			back="The study of life.",
		)
		self.client.force_login(self.student_user)

		response = self.client.post(
			reverse("complete_flashcard_session", args=[note.id])
		)

		self.assertRedirects(
			response,
			reverse("study_flashcards", args=[note.id]),
			fetch_redirect_response=False,
		)
		self.assertEqual(get_study_streak(self.student), 1)
		self.assertEqual(StudyDay.objects.filter(student=self.student).count(), 1)

		dashboard_response = self.client.get(reverse("student_dashboard"))
		self.assertContains(dashboard_response, "Current Streak")
		self.assertEqual(dashboard_response.context["current_streak"], 1)

	def test_quiz_submission_records_a_study_day(self):
		quiz = Quiz.objects.create(student=self.student, subject="Biology")
		self.client.force_login(self.student_user)

		response = self.client.post(reverse("submit_quiz", args=[quiz.id]))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(get_study_streak(self.student), 1)

	def test_parent_dashboard_shows_linked_students_streak(self):
		parent_user = User.objects.create_user(
			username="streak-parent@example.com",
			email="streak-parent@example.com",
			password="test-password",
		)
		Parent.objects.create(user=parent_user, student=self.student)
		record_study_day(self.student)
		self.client.force_login(parent_user)

		response = self.client.get(reverse("parent_dashboard"))

		self.assertContains(response, "Current Study Streak")
		self.assertEqual(response.context["current_streak"], 1)


class QuizQuestionCountTests(TestCase):
	def setUp(self):
		self.media_directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.media_directory.cleanup)
		media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
		media_settings.enable()
		self.addCleanup(media_settings.disable)

		self.user = User.objects.create_user(
			username="quiz-count@example.com",
			email="quiz-count@example.com",
			password="test-password",
		)
		self.student = Student.objects.create(user=self.user, class_semester="BCA")
		self.note = Notes.objects.create(
			student=self.student,
			subject="Biology",
			file=SimpleUploadedFile(
				"biology.txt",
				(
					"Photosynthesis transforms bright sunlight into chemical energy inside green leaves of plants. "
					"Respiration releases stored chemical energy through coordinated cellular reactions in living organisms. "
					"Mitochondria produce usable energy through specialized reactions inside many eukaryotic cells. "
					"Chlorophyll absorbs visible wavelengths during important stages of photosynthesis in plant cells. "
					"Enzymes accelerate biochemical reactions without being permanently consumed during cellular metabolism. "
					"Diffusion moves particles from concentrated regions toward areas with lower concentration over time."
				).encode(),
			),
		)
		self.client.force_login(self.user)

	@staticmethod
	def _gemini_response(count):
		questions = [
			{
				"question": f"Which answer belongs to biology question {index}?",
				"topic": f"Topic {index % 3}",
				"options": [f"Answer {index}", f"Choice B {index}", f"Choice C {index}", f"Choice D {index}"],
				"answer": f"Answer {index}",
			}
			for index in range(count)
		]
		return SimpleNamespace(text=json.dumps(questions))

	def test_quiz_center_offers_supported_question_counts(self):
		response = self.client.get(reverse("quiz_home"))

		self.assertContains(response, 'name="question_count"')
		for count in (5, 10, 20, 30):
			self.assertContains(response, f"{count} questions")

	@patch("core.views.genai.Client")
	def test_selected_count_is_used_for_ai_generation(self, gemini_client):
		gemini_client.return_value.models.generate_content.return_value = self._gemini_response(10)

		response = self.client.post(
			reverse("generate_quiz", args=[self.note.id]),
			{"question_count": "10"},
		)

		quiz = Quiz.objects.get(student=self.student)
		self.assertRedirects(
			response,
			reverse("take_quiz", args=[quiz.id]),
			fetch_redirect_response=False,
		)
		self.assertEqual(Question.objects.filter(quiz=quiz).count(), 10)
		self.assertEqual(Question.objects.filter(quiz=quiz, topic="Topic 0").count(), 4)
		prompt = gemini_client.return_value.models.generate_content.call_args.kwargs["contents"]
		self.assertIn("Generate exactly 10", prompt)

	@patch("core.views.genai.Client")
	def test_short_ai_response_is_topped_up_from_note_text(self, gemini_client):
		gemini_client.return_value.models.generate_content.return_value = self._gemini_response(2)

		response = self.client.post(
			reverse("generate_quiz", args=[self.note.id]),
			{"question_count": "5"},
		)

		quiz = Quiz.objects.get(student=self.student)
		self.assertEqual(Question.objects.filter(quiz=quiz).count(), 5)
		self.assertEqual(response.status_code, 302)

	@patch("core.views.genai.Client")
	def test_short_note_reports_actual_count_on_quiz_page(self, gemini_client):
		gemini_client.return_value.models.generate_content.return_value = self._gemini_response(2)

		response = self.client.post(
			reverse("generate_quiz", args=[self.note.id]),
			{"question_count": "30"},
			follow=True,
		)

		quiz = Quiz.objects.get(student=self.student)
		actual_count = Question.objects.filter(quiz=quiz).count()
		self.assertLess(actual_count, 30)
		self.assertContains(
			response,
			f"This note supported {actual_count} of your 30 requested questions.",
		)

	@patch("core.views.genai.Client")
	def test_unsupported_count_is_rejected_without_creating_quiz(self, gemini_client):
		response = self.client.post(
			reverse("generate_quiz", args=[self.note.id]),
			{"question_count": "7"},
		)

		self.assertRedirects(response, reverse("quiz_home"), fetch_redirect_response=False)
		self.assertFalse(Quiz.objects.filter(student=self.student).exists())
		gemini_client.assert_not_called()


class TopicAnalyticsTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="topic-student@example.com",
			email="topic-student@example.com",
			password="test-password",
		)
		self.student = Student.objects.create(user=self.user, class_semester="BCA")
		self.client.force_login(self.user)

	def test_quiz_answers_create_topic_accuracy_and_recommendation(self):
		quiz = Quiz.objects.create(student=self.student, subject="Biology")
		questions = [
			Question.objects.create(
				quiz=quiz,
				question_text=f"Question {index}",
				topic=topic,
				option_a="Correct",
				option_b="Incorrect",
				option_c="Another option",
				option_d="Last option",
				correct_answer="Correct",
			)
			for index, topic in enumerate(
				["Cell biology", "Cell biology", "Genetics", "Genetics"]
			)
		]
		answers = {
			str(questions[0].id): "Incorrect",
			str(questions[1].id): "Incorrect",
			str(questions[2].id): "Correct",
			str(questions[3].id): "Correct",
		}

		response = self.client.post(reverse("submit_quiz", args=[quiz.id]), answers)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(QuestionAnswer.objects.filter(question__quiz=quiz).count(), 4)
		performance = get_topic_performance(self.student)
		self.assertEqual(
			[(item["topic"], item["accuracy"]) for item in performance],
			[("Cell biology", 0), ("Genetics", 100)],
		)
		self.assertEqual(get_recommended_topic(performance)["topic"], "Cell biology")

		progress_response = self.client.get(reverse("student_progress"))
		self.assertContains(progress_response, "Give Cell biology another review")
		self.assertContains(progress_response, "Topic accuracy")
		self.assertEqual(progress_response.context["recommended_topic"]["topic"], "Cell biology")
