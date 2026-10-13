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


class NoteDeletionAndSecurityTests(TestCase):
	def setUp(self):
		self.user1 = User.objects.create_user(
			username="student1@example.com",
			email="student1@example.com",
			password="password1",
		)
		self.student1 = Student.objects.create(user=self.user1, class_semester="BCA")

		self.user2 = User.objects.create_user(
			username="student2@example.com",
			email="student2@example.com",
			password="password2",
		)
		self.student2 = Student.objects.create(user=self.user2, class_semester="BCA")

		self.note1 = Notes.objects.create(
			student=self.student1,
			subject="Chemistry",
			file=SimpleUploadedFile("chem.txt", b"Covalent and ionic bonds in chemistry."),
		)
		self.quiz1 = Quiz.objects.create(student=self.student1, subject="Chemistry")
		self.question1 = Question.objects.create(
			quiz=self.quiz1,
			question_text="What is a covalent bond?",
			topic="Bonding",
			option_a="Shared electrons",
			option_b="Transfer electrons",
			option_c="No interaction",
			option_d="Nuclear force",
			correct_answer="Shared electrons",
		)

	def test_delete_note_url_and_alias(self):
		self.client.force_login(self.user1)
		response = self.client.get(reverse("delete_note", args=[self.note1.id]))
		self.assertRedirects(response, reverse("student_notes"))
		self.assertFalse(Notes.objects.filter(id=self.note1.id).exists())

	def test_student_cannot_take_another_students_quiz(self):
		self.client.force_login(self.user2)
		response = self.client.get(reverse("take_quiz", args=[self.quiz1.id]))
		self.assertEqual(response.status_code, 404)

	def test_view_quiz_result_renders_student_answers(self):
		self.client.force_login(self.user1)
		QuestionAnswer.objects.create(
			question=self.question1,
			selected_answer="Shared electrons",
			is_correct=True,
		)
		response = self.client.get(reverse("view_quiz_result", args=[self.quiz1.id]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Shared electrons")
		self.assertContains(response, "Correct")

	def test_view_note_authorization(self):
		# Student owner can view
		self.client.force_login(self.user1)
		response = self.client.get(reverse("view_note", args=[self.note1.id]))
		self.assertEqual(response.status_code, 200)

		# Another student is denied (404)
		self.client.force_login(self.user2)
		response = self.client.get(reverse("view_note", args=[self.note1.id]))
		self.assertEqual(response.status_code, 404)

		# Linked parent can view
		parent_user = User.objects.create_user(
			username="parent@example.com",
			email="parent@example.com",
			password="password3",
		)
		Parent.objects.create(user=parent_user, student=self.student1)
		self.client.force_login(parent_user)
		response = self.client.get(reverse("view_note", args=[self.note1.id]))
		self.assertEqual(response.status_code, 200)


class ApiAndServiceLayerTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			username="api_student@example.com",
			email="api_student@example.com",
			password="test-password",
		)
		self.student = Student.objects.create(user=self.user, class_semester="MCA")
		self.note = Notes.objects.create(
			student=self.student,
			subject="Computer Networks",
			file=SimpleUploadedFile("networks.txt", b"OSI model has seven distinct layers."),
		)

	def test_api_health_endpoint(self):
		response = self.client.get(reverse("api_health"))
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data["status"], "success")
		self.assertEqual(data["data"]["status"], "healthy")

	def test_api_streak_endpoint_authenticated(self):
		self.client.force_login(self.user)
		record_study_day(self.student)
		response = self.client.get(reverse("api_streak"))
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data["status"], "success")
		self.assertEqual(data["data"]["current_streak"], 1)

	def test_api_notes_list(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("api_notes_list"))
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(len(data["data"]["notes"]), 1)
		self.assertEqual(data["data"]["notes"][0]["subject"], "Computer Networks")


class ProductionSecurityAndConfigurationTests(TestCase):
	def test_debug_defaults_to_false_in_production(self):
		from django.conf import settings
		# In this test environment with our updated settings, verify DEBUG is not True by default
		# unless explicitly overridden.
		self.assertFalse(settings.DEBUG)

	def test_anonymous_user_redirected_from_all_protected_views(self):
		protected_urls = [
			reverse("student_dashboard"),
			reverse("student_notes"),
			reverse("quiz_home"),
			reverse("flashcard_home"),
			reverse("pomodoro_timer"),
			reverse("student_progress"),
		]
		for url in protected_urls:
			response = self.client.get(url)
			self.assertEqual(response.status_code, 302, f"URL {url} did not redirect anonymous user.")
			self.assertIn("/login", response.url)

	def test_student_cannot_view_another_student_quiz_result(self):
		user_a = User.objects.create_user(username="student_a@test.com", password="pass")
		student_a = Student.objects.create(user=user_a, class_semester="BCA")
		quiz_a = Quiz.objects.create(student=student_a, subject="History")

		user_b = User.objects.create_user(username="student_b@test.com", password="pass")
		Student.objects.create(user=user_b, class_semester="BCA")

		self.client.force_login(user_b)
		response = self.client.get(reverse("view_quiz_result", args=[quiz_a.id]))
		self.assertEqual(response.status_code, 404)

	def test_parent_authorization_for_quiz_results(self):
		student_user = User.objects.create_user(username="child@test.com", password="pass")
		student = Student.objects.create(user=student_user, class_semester="BCA")
		quiz = Quiz.objects.create(student=student, subject="Math")

		linked_parent_user = User.objects.create_user(username="parent_linked@test.com", password="pass")
		Parent.objects.create(user=linked_parent_user, student=student)

		other_student_user = User.objects.create_user(username="other_child@test.com", password="pass")
		other_student = Student.objects.create(user=other_student_user, class_semester="BCA")
		unlinked_parent_user = User.objects.create_user(username="parent_unlinked@test.com", password="pass")
		Parent.objects.create(user=unlinked_parent_user, student=other_student)

		# Linked parent can view
		self.client.force_login(linked_parent_user)
		response = self.client.get(reverse("view_quiz_result", args=[quiz.id]))
		self.assertEqual(response.status_code, 200)

		# Unlinked parent receives 404
		self.client.force_login(unlinked_parent_user)
		response = self.client.get(reverse("view_quiz_result", args=[quiz.id]))
		self.assertEqual(response.status_code, 404)


class UploadValidationAndStorageQuotaTests(TestCase):
	def setUp(self):
		self.media_directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.media_directory.cleanup)
		media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
		media_settings.enable()
		self.addCleanup(media_settings.disable)

		self.user = User.objects.create_user(username="upload_student@test.com", password="pass")
		self.student = Student.objects.create(user=self.user, class_semester="BCA")
		self.client.force_login(self.user)

	def test_valid_text_upload_succeeds(self):
		valid_content = b"This is a valid educational study note containing sufficient text content to pass all validation checks."
		uploaded_file = SimpleUploadedFile("study_notes.txt", valid_content, content_type="text/plain")
		response = self.client.post(reverse("student_notes"), {
			"subject": "Physics",
			"file": uploaded_file,
		})
		self.assertRedirects(response, reverse("student_notes"))
		self.assertTrue(Notes.objects.filter(student=self.student, subject="Physics").exists())
		note = Notes.objects.get(student=self.student, subject="Physics")
		self.assertEqual(note.file_size, len(valid_content))
		if hasattr(note.file, "close"):
			note.file.close()

	def test_unsupported_file_extension_rejected(self):
		unsupported_file = SimpleUploadedFile("script.py", b"print('malicious code here')", content_type="text/x-python")
		response = self.client.post(reverse("student_notes"), {
			"subject": "Insecure File",
			"file": unsupported_file,
		})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(Notes.objects.filter(student=self.student, subject="Insecure File").exists())
		self.assertContains(response, "Unsupported file format")

	def test_empty_file_rejected(self):
		empty_file = SimpleUploadedFile("empty.txt", b"", content_type="text/plain")
		response = self.client.post(reverse("student_notes"), {
			"subject": "Empty Document",
			"file": empty_file,
		})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(Notes.objects.filter(student=self.student, subject="Empty Document").exists())
		self.assertContains(response, "file is empty")

	def test_oversized_file_rejected(self):
		with override_settings(MAX_UPLOAD_SIZE_BYTES=100):
			big_file = SimpleUploadedFile("big.txt", b"A" * 200, content_type="text/plain")
			response = self.client.post(reverse("student_notes"), {
				"subject": "Oversized",
				"file": big_file,
			})
			self.assertEqual(response.status_code, 200)
			self.assertFalse(Notes.objects.filter(student=self.student, subject="Oversized").exists())
			self.assertContains(response, "exceeds the maximum allowed size")

	def test_corrupted_pdf_rejected(self):
		bad_pdf = SimpleUploadedFile("corrupt.pdf", b"%PDF-1.4\ncorrupted content that cannot be parsed by pypdf", content_type="application/pdf")
		response = self.client.post(reverse("student_notes"), {
			"subject": "Corrupt Note",
			"file": bad_pdf,
		})
		self.assertEqual(response.status_code, 200)
		self.assertFalse(Notes.objects.filter(student=self.student, subject="Corrupt Note").exists())

	def test_per_user_storage_quota_enforced(self):
		with override_settings(MAX_USER_STORAGE_BYTES=160):
			content1 = b"First note with enough valid words to pass validation cleanly and successfully."
			file1 = SimpleUploadedFile("n1.txt", content1, content_type="text/plain")
			self.client.post(reverse("student_notes"), {"subject": "Note 1", "file": file1})
			self.assertEqual(Notes.objects.filter(student=self.student).count(), 1)

			# Second upload that pushes student total over 160 bytes
			content2 = b"Second note with more content words pushing storage above limits." * 3
			file2 = SimpleUploadedFile("n2.txt", content2, content_type="text/plain")
			response = self.client.post(reverse("student_notes"), {"subject": "Note 2", "file": file2})
			self.assertEqual(response.status_code, 200)
			self.assertContains(response, "Storage quota exceeded")
			self.assertEqual(Notes.objects.filter(student=self.student).count(), 1)

	def test_deleting_note_cleans_up_file_without_affecting_other_students(self):
		other_user = User.objects.create_user(username="other_up@test.com", password="pass")
		other_student = Student.objects.create(user=other_user, class_semester="BCA")

		note1 = Notes.objects.create(
			student=self.student,
			subject="Student 1 Note",
			file=SimpleUploadedFile("s1.txt", b"Student 1 notes text content here."),
			file_size=35,
		)
		note2 = Notes.objects.create(
			student=other_student,
			subject="Student 2 Note",
			file=SimpleUploadedFile("s2.txt", b"Student 2 notes text content here."),
			file_size=35,
		)
		file1_storage = note1.file.storage
		file1_name = note1.file.name
		file2_name = note2.file.name

		self.assertTrue(file1_storage.exists(file1_name))
		self.assertTrue(file1_storage.exists(file2_name))

		# Delete note 1
		response = self.client.get(reverse("delete_note", args=[note1.id]))
		self.assertRedirects(response, reverse("student_notes"))
		self.assertFalse(file1_storage.exists(file1_name))
		self.assertTrue(file1_storage.exists(file2_name))


class AIGenerationReliabilityTests(TestCase):
	def setUp(self):
		self.media_directory = tempfile.TemporaryDirectory()
		self.addCleanup(self.media_directory.cleanup)
		media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
		media_settings.enable()
		self.addCleanup(media_settings.disable)

		self.user = User.objects.create_user(username="ai_student@test.com", password="pass")
		self.student = Student.objects.create(user=self.user, class_semester="BCA")
		self.note = Notes.objects.create(
			student=self.student,
			subject="Astronomy",
			file=SimpleUploadedFile(
				"astronomy.txt",
				(
					"The solar system consists of eight major planets orbiting the central Sun. "
					"Jupiter is the largest planet in our solar system with immense gravitational force. "
					"Mars is commonly known as the Red Planet due to iron oxide minerals on its surface. "
					"Venus possesses an extremely dense carbon dioxide atmosphere with runaway greenhouse warming. "
					"Saturn has prominent reflective planetary rings composed primarily of water ice chunks."
				).encode(),
			),
		)
		self.client.force_login(self.user)

	@patch("core.views.genai.Client")
	def test_malformed_json_falls_back_to_nlp_cleanly(self, gemini_client):
		gemini_client.return_value.models.generate_content.return_value = SimpleNamespace(
			text="```json [{\"question\": \"Incomplete JSON...",
		)
		response = self.client.post(
			reverse("generate_quiz", args=[self.note.id]),
			{"question_count": "5"},
		)
		self.assertEqual(response.status_code, 302)
		quiz = Quiz.objects.get(student=self.student)
		questions = Question.objects.filter(quiz=quiz)
		self.assertGreaterEqual(questions.count(), 1)
		for q in questions:
			self.assertEqual(len(set([q.option_a, q.option_b, q.option_c, q.option_d])), 4)
			self.assertIn(q.correct_answer, [q.option_a, q.option_b, q.option_c, q.option_d])

	@patch("core.views.genai.Client")
	def test_quarantines_invalid_answers_and_missing_options(self, gemini_client):
		# First item has only 2 options; second item has answer not in options; third item is valid
		gemini_client.return_value.models.generate_content.return_value = SimpleNamespace(
			text=json.dumps([
				{"question": "Broken options question", "options": ["A", "B"], "answer": "A"},
				{"question": "Mismatched answer question", "options": ["A", "B", "C", "D"], "answer": "Z"},
				{
					"question": "Which planet is largest in the solar system?",
					"topic": "Planets",
					"options": ["Jupiter", "Mars", "Venus", "Earth"],
					"answer": "Jupiter",
					"explanation": "Jupiter has the largest mass and diameter among all planets.",
					"difficulty": "easy",
				},
			])
		)
		response = self.client.post(
			reverse("generate_quiz", args=[self.note.id]),
			{"question_count": "5"},
		)
		self.assertEqual(response.status_code, 302)
		quiz = Quiz.objects.get(student=self.student)
		valid_q = Question.objects.filter(quiz=quiz, question_text="Which planet is largest in the solar system?").first()
		self.assertIsNotNone(valid_q)
		self.assertEqual(valid_q.explanation, "Jupiter has the largest mass and diameter among all planets.")
		self.assertEqual(valid_q.difficulty, "easy")
		self.assertFalse(Question.objects.filter(quiz=quiz, question_text="Broken options question").exists())
		self.assertFalse(Question.objects.filter(quiz=quiz, question_text="Mismatched answer question").exists())

	def test_report_question_view_persists_feedback(self):
		from core.models import QuestionReport
		quiz = Quiz.objects.create(student=self.student, subject="Astronomy")
		question = Question.objects.create(
			quiz=quiz,
			question_text="What is Mars?",
			option_a="Red Planet",
			option_b="Gas Giant",
			option_c="Star",
			option_d="Comet",
			correct_answer="Red Planet",
		)
		response = self.client.post(
			reverse("report_question", args=[question.id]),
			{"reason": "Option text is too brief and could be clearer."},
		)
		self.assertRedirects(response, reverse("view_quiz_result", args=[quiz.id]))
		self.assertTrue(QuestionReport.objects.filter(question=question, student=self.student).exists())
		report = QuestionReport.objects.get(question=question)
		self.assertIn("too brief", report.reason)


class StudySuiteFeatureTests(TestCase):
	"""Tests for Interactive Flowcharts, Cornell Short Notes, and Quiz Remediation."""

	def setUp(self):
		self.student_user = User.objects.create_user(username="suite_student", password="Password123!")
		self.other_user = User.objects.create_user(username="other_student", password="Password123!")
		self.student = Student.objects.create(user=self.student_user, class_semester="Sem 4")
		self.other_student = Student.objects.create(user=self.other_user, class_semester="Sem 4")
		self.client.force_login(self.student_user)

		# Create a sample note
		sample_content = (
			"Photosynthesis is the biological process used by plants to convert light energy into chemical energy. "
			"Chlorophyll is defined as the green pigment responsible for light absorption. "
			"The light-dependent reaction produces ATP and NADPH in the thylakoid membrane. "
			"The Calvin cycle fixes carbon dioxide into glucose within the stroma."
		)
		self.note = Notes.objects.create(
			student=self.student,
			subject="Plant Biology",
			file=SimpleUploadedFile("biology.txt", sample_content.encode("utf-8")),
			file_size=len(sample_content),
		)

	def test_flowchart_service_and_view(self):
		from core.services.study_suite_service import generate_flowchart_for_note
		chart = generate_flowchart_for_note(self.note, diagram_type="flowchart")
		self.assertIsNotNone(chart)
		self.assertIn("Plant Biology", chart.title)
		self.assertIn("graph TD", chart.mermaid_code)

		# Test view renders successfully
		response = self.client.get(reverse("note_flowchart", args=[self.note.id]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Plant Biology")
		self.assertContains(response, "graph TD")

		# Test switching diagram type to mindmap
		mm_response = self.client.get(reverse("note_flowchart", args=[self.note.id]) + "?type=mindmap")
		self.assertEqual(mm_response.status_code, 200)
		self.assertContains(mm_response, "mindmap")

	def test_shortnotes_service_and_view(self):
		from core.services.study_suite_service import generate_shortnotes_for_note
		short_note = generate_shortnotes_for_note(self.note)
		self.assertIsNotNone(short_note)
		self.assertTrue(len(short_note.executive_summary) > 10)
		self.assertTrue(len(short_note.cornell_cues) > 0)
		self.assertTrue(len(short_note.key_definitions) > 0)

		# Test view renders successfully
		response = self.client.get(reverse("note_shortnotes", args=[self.note.id]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Cornell Active Recall System")
		self.assertContains(response, short_note.executive_summary[:25])

	def test_quiz_remediation_and_resolution(self):
		from core.models import Question, QuestionAnswer, RemediationReview
		quiz = Quiz.objects.create(student=self.student, subject="Plant Biology")
		q = Question.objects.create(
			quiz=quiz,
			question_text="Where does the Calvin cycle take place?",
			topic="Photosynthesis",
			option_a="Thylakoid",
			option_b="Stroma",
			option_c="Mitochondria",
			option_d="Ribosome",
			correct_answer="Stroma",
			explanation="The Calvin cycle fixes carbon in the stroma of chloroplasts.",
		)
		# Record incorrect answer
		QuestionAnswer.objects.create(
			question=q,
			selected_answer="Thylakoid",
			is_correct=False,
		)

		# View remediation workout
		response = self.client.get(reverse("quiz_remediation", args=[quiz.id]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Targeted Concept Remediation")
		self.assertContains(response, "Photosynthesis")

		remed = RemediationReview.objects.filter(quiz=quiz, student=self.student).first()
		self.assertIsNotNone(remed)
		self.assertFalse(remed.is_resolved)

		# Submit correct answer to resolve the remediation check
		post_resp = self.client.post(
			reverse("resolve_remediation", args=[remed.id]),
			{"selected_option": remed.correct_answer},
		)
		self.assertEqual(post_resp.status_code, 200)
		data = post_resp.json()
		self.assertTrue(data["is_correct"])
		self.assertTrue(data["is_resolved"])

		remed.refresh_from_db()
		self.assertTrue(remed.is_resolved)

	def test_permission_denied_for_other_student(self):
		self.client.force_login(self.other_user)
		chart_resp = self.client.get(reverse("note_flowchart", args=[self.note.id]))
		self.assertEqual(chart_resp.status_code, 404)

		notes_resp = self.client.get(reverse("note_shortnotes", args=[self.note.id]))
		self.assertEqual(notes_resp.status_code, 404)


class MistakeNotebookTests(TestCase):
	def setUp(self):
		self.student_user = User.objects.create_user(username="mistake_student@test.com", password="password")
		self.other_user = User.objects.create_user(username="other_student@test.com", password="password")
		self.student = Student.objects.create(user=self.student_user, class_semester="Sem 4")
		self.other_student = Student.objects.create(user=self.other_user, class_semester="Sem 4")
		self.client.force_login(self.student_user)

		self.quiz = Quiz.objects.create(student=self.student, subject="Database Systems")
		self.question = Question.objects.create(
			quiz=self.quiz,
			question_text="What does ACID stand for in DBMS?",
			topic="Transactions",
			option_a="Atomicity, Consistency, Isolation, Durability",
			option_b="Access, Control, Index, Data",
			option_c="Array, Class, Interface, Delegate",
			option_d="Automated, Concurrent, Isolated, Distributed",
			correct_answer="Atomicity, Consistency, Isolation, Durability",
			explanation="ACID guarantees reliable processing of database transactions.",
		)

	def test_incorrect_quiz_answer_automatically_records_mistake(self):
		from core.services.quiz_service import evaluate_quiz_submission
		from core.models import MistakeRecord, ScheduledReview

		# Submit incorrect answer
		evaluate_quiz_submission(self.quiz, {str(self.question.id): "Access, Control, Index, Data"})

		mistake = MistakeRecord.objects.filter(student=self.student, question=self.question).first()
		self.assertIsNotNone(mistake)
		self.assertEqual(mistake.mistake_count, 1)
		self.assertEqual(mistake.selected_answer, "Access, Control, Index, Data")
		self.assertEqual(mistake.status, "unresolved")
		self.assertTrue(mistake.is_in_revision)

		# Check spaced repetition record was created
		review = ScheduledReview.objects.filter(student=self.student, mistake_record=mistake).first()
		self.assertIsNotNone(review)
		self.assertEqual(review.status, "due")

	def test_repeated_mistakes_update_frequency_and_reset_unresolved(self):
		from core.services.quiz_service import evaluate_quiz_submission
		from core.models import MistakeRecord

		# Miss once
		evaluate_quiz_submission(self.quiz, {str(self.question.id): "Option B"})
		mistake = MistakeRecord.objects.get(student=self.student, question=self.question)
		self.assertEqual(mistake.mistake_count, 1)

		# Miss second time
		evaluate_quiz_submission(self.quiz, {str(self.question.id): "Option C"})
		mistake.refresh_from_db()
		self.assertEqual(mistake.mistake_count, 2)
		self.assertEqual(mistake.selected_answer, "Option C")
		self.assertEqual(mistake.status, "unresolved")

	def test_remove_mistake_from_revision_preserves_quiz_history(self):
		from core.services.quiz_service import evaluate_quiz_submission
		from core.models import MistakeRecord, QuestionAnswer

		evaluate_quiz_submission(self.quiz, {str(self.question.id): "Option B"})
		mistake = MistakeRecord.objects.get(student=self.student, question=self.question)

		# Remove from active revision list
		resp = self.client.post(reverse("toggle_mistake_revision", args=[mistake.id]), {"action": "remove"})
		self.assertEqual(resp.status_code, 302)

		mistake.refresh_from_db()
		self.assertFalse(mistake.is_in_revision)

		# Historical quiz QuestionAnswer record remains intact
		qa = QuestionAnswer.objects.filter(question=self.question).first()
		self.assertIsNotNone(qa)
		self.assertFalse(qa.is_correct)

	def test_student_cannot_access_another_students_mistakes(self):
		from core.models import MistakeRecord
		other_mistake = MistakeRecord.objects.create(
			student=self.other_student,
			subject="OS",
			topic="Deadlock",
			question_text="What causes deadlock?",
			correct_answer="Circular wait",
		)
		resp = self.client.get(reverse("mistake_detail", args=[other_mistake.id]))
		self.assertEqual(resp.status_code, 404)

		post_resp = self.client.post(reverse("toggle_mistake_revision", args=[other_mistake.id]))
		self.assertEqual(post_resp.status_code, 404)


class RetryQuizTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="retry_user@test.com", password="password")
		self.student = Student.objects.create(user=self.user, class_semester="Sem 4")
		self.client.force_login(self.user)

		self.quiz = Quiz.objects.create(student=self.student, subject="Operating Systems")
		self.q1 = Question.objects.create(
			quiz=self.quiz,
			question_text="What is a mutex?",
			topic="Concurrency",
			option_a="Mutual exclusion object",
			option_b="Memory unallocated table",
			option_c="Multi-tasking executor",
			option_d="Microcode unit",
			correct_answer="Mutual exclusion object",
			explanation="Mutex prevents concurrent access to critical sections.",
		)

	def test_generates_valid_retry_quiz_from_mistakes(self):
		from core.services.quiz_service import evaluate_quiz_submission
		from core.services.retry_quiz_service import generate_retry_quiz
		from core.models import MistakeRecord

		# Fail question
		evaluate_quiz_submission(self.quiz, {str(self.q1.id): "Microcode unit"})
		mistake = MistakeRecord.objects.get(student=self.student)

		# Generate retry quiz in 'mistakes' mode
		retry_quiz = generate_retry_quiz(self.student, mode="mistakes", question_count=3)
		self.assertIsNotNone(retry_quiz)
		self.assertEqual(retry_quiz.student, self.student)
		self.assertTrue(retry_quiz.question_set.count() >= 1)

		# Verify options are valid and have correct answers
		for q in retry_quiz.question_set.all():
			options = [q.option_a, q.option_b, q.option_c, q.option_d]
			self.assertIn(q.correct_answer, options)
			self.assertEqual(len(set(options)), 4)

	def test_correct_retry_submission_advances_mistake_mastery(self):
		from core.services.quiz_service import evaluate_quiz_submission
		from core.models import MistakeRecord

		# Miss initially
		evaluate_quiz_submission(self.quiz, {str(self.q1.id): "Wrong"})
		mistake = MistakeRecord.objects.get(student=self.student, question=self.q1)
		self.assertEqual(mistake.status, "unresolved")

		# Create a retry quiz targeting this exact question
		retry_quiz = Quiz.objects.create(student=self.student, subject="Retry Practice")
		retry_q = Question.objects.create(
			quiz=retry_quiz,
			question_text=self.q1.question_text,
			topic=self.q1.topic,
			option_a=self.q1.option_a,
			option_b=self.q1.option_b,
			option_c=self.q1.option_c,
			option_d=self.q1.option_d,
			correct_answer=self.q1.correct_answer,
		)
		# Now answer correctly
		evaluate_quiz_submission(retry_quiz, {str(retry_q.id): self.q1.correct_answer})
		mistake.refresh_from_db()
		self.assertEqual(mistake.status, "reviewing")


class SpacedRepetitionTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="sr_student@test.com", password="password")
		self.student = Student.objects.create(user=self.user, class_semester="Sem 4")
		self.client.force_login(self.user)

	def test_schedule_and_prevent_duplicate_reviews(self):
		from core.services.spaced_repetition_service import schedule_concept_review
		from core.models import ScheduledReview

		r1 = schedule_concept_review(
			student=self.student,
			concept_name="Binary Search Trees",
			subject="Data Structures",
			topic="Trees",
			payload={"definition": "A sorted tree structure"},
		)
		self.assertIsNotNone(r1)

		# Second identical call should update, not create duplicate
		r2 = schedule_concept_review(
			student=self.student,
			concept_name="Binary Search Trees",
			subject="Data Structures",
			topic="Trees",
			payload={"definition": "A sorted tree structure updated"},
		)
		self.assertEqual(r1.id, r2.id)
		self.assertEqual(ScheduledReview.objects.filter(student=self.student).count(), 1)

	def test_adaptive_intervals_on_confidence_ratings(self):
		from core.services.spaced_repetition_service import schedule_concept_review, process_review_attempt

		review = schedule_concept_review(
			student=self.student,
			concept_name="Graph Traversal",
			subject="Algorithms",
			topic="Graphs",
			payload={},
		)
		self.assertEqual(review.interval_days, 1.0)

		# Rate 'good' -> interval increases
		process_review_attempt(review, was_correct=True, confidence="good")
		review.refresh_from_db()
		self.assertTrue(review.interval_days >= 3.0)
		self.assertEqual(review.consecutive_correct, 1)

		# Rate 'high' -> interval expands significantly
		process_review_attempt(review, was_correct=True, confidence="high")
		review.refresh_from_db()
		self.assertTrue(review.interval_days >= 7.0)
		self.assertEqual(review.consecutive_correct, 2)

		# Fail ('again') -> resets interval to 1.0
		process_review_attempt(review, was_correct=False, confidence="again")
		review.refresh_from_db()
		self.assertEqual(review.interval_days, 1.0)
		self.assertEqual(review.consecutive_correct, 0)


class VisualFlowchartMindmapTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="diag_user@test.com", password="password")
		self.other = User.objects.create_user(username="other_diag@test.com", password="password")
		self.student = Student.objects.create(user=self.user, class_semester="Sem 4")
		self.other_student = Student.objects.create(user=self.other, class_semester="Sem 4")
		self.client.force_login(self.user)

		content = b"Database normalization organizes fields and tables of a relational database."
		self.note = Notes.objects.create(
			student=self.student,
			subject="Database Management",
			file=SimpleUploadedFile("db.txt", content),
			file_size=len(content),
		)

	def test_supports_all_seven_diagram_modes(self):
		from core.services.study_suite_service import generate_flowchart_for_note

		modes = ["flowchart", "mindmap", "concept", "sequence", "timeline", "comparison", "hierarchy"]
		for mode in modes:
			chart = generate_flowchart_for_note(self.note, diagram_type=mode, force_refresh=True)
			self.assertIsNotNone(chart)
			self.assertEqual(chart.diagram_type, mode)
			self.assertTrue(len(chart.mermaid_code) > 10)

	def test_validate_mermaid_syntax_rejects_unsafe_input(self):
		from core.services.study_suite_service import validate_mermaid_syntax

		# Valid flowchart
		valid, _ = validate_mermaid_syntax("graph TD\n  A --> B")
		self.assertTrue(valid)

		# XSS attempt
		invalid, msg = validate_mermaid_syntax("graph TD\n  A[<script>alert(1)</script>] --> B")
		self.assertFalse(invalid)
		self.assertIn("disallowed", msg)

		# Unmatched brackets
		invalid_syntax, err = validate_mermaid_syntax("graph TD\n  A[Incomplete Node --> B")
		self.assertFalse(invalid_syntax)
		self.assertIn("Unbalanced", err)

	def test_saving_source_creates_version_snapshot(self):
		from core.services.study_suite_service import generate_flowchart_for_note
		from core.models import DiagramVersion

		chart = generate_flowchart_for_note(self.note, diagram_type="flowchart")
		initial_count = DiagramVersion.objects.filter(flowchart=chart).count()

		new_code = "graph TD\n  Start --> Next"
		resp = self.client.post(
			reverse("save_flowchart_source", args=[chart.id]),
			{"title": "Edited Chart", "mermaid_code": new_code},
		)
		self.assertEqual(resp.status_code, 200)

		chart.refresh_from_db()
		self.assertEqual(chart.mermaid_code, new_code)
		self.assertEqual(DiagramVersion.objects.filter(flowchart=chart).count(), initial_count + 1)

	def test_diagram_test_me_records_missed_concepts(self):
		from core.services.study_suite_service import generate_flowchart_for_note
		from core.models import MistakeRecord

		chart = generate_flowchart_for_note(self.note, diagram_type="concept")

		# Submit diagram test with incorrect answer
		resp = self.client.post(reverse("diagram_test_me", args=[chart.id]), {
			"total_questions": "1",
			"q_0_text": "What is normalization?",
			"q_0_selected": "Wrong Process",
			"q_0_correct": "Organizing fields to reduce redundancy",
			"q_0_topic": "Normalization",
			"q_0_expl": "Normalization minimizes duplication.",
		})
		self.assertEqual(resp.status_code, 200)
		self.assertContains(resp, "Diagram Verification Complete")

		# Verify MistakeRecord was created
		m = MistakeRecord.objects.filter(student=self.student, question_text="What is normalization?").first()
		self.assertIsNotNone(m)
		self.assertEqual(m.status, "unresolved")


class CornellNotesAndCheatSheetsTests(TestCase):
	def setUp(self):
		self.user = User.objects.create_user(username="notes_user@test.com", password="password")
		self.student = Student.objects.create(user=self.user, class_semester="Sem 4")
		self.client.force_login(self.user)

		content = b"TCP is a connection-oriented protocol. UDP is a connectionless protocol."
		self.note = Notes.objects.create(
			student=self.student,
			subject="Computer Networks",
			file=SimpleUploadedFile("net.txt", content),
			file_size=len(content),
		)

	def test_generates_multiple_modes_and_cues(self):
		from core.services.study_suite_service import generate_shortnotes_for_note

		short_note = generate_shortnotes_for_note(self.note, mode="cheatsheet", length_option="short")
		self.assertIsNotNone(short_note)
		self.assertEqual(short_note.mode, "cheatsheet")
		self.assertTrue(len(short_note.executive_summary) > 0)
		self.assertTrue(len(short_note.cornell_cues) > 0)

	def test_create_flashcards_from_cues_without_duplicates(self):
		from core.services.study_suite_service import generate_shortnotes_for_note, create_flashcards_from_shortnote
		from core.models import Flashcard

		short_note = generate_shortnotes_for_note(self.note, mode="cornell")
		created_first = create_flashcards_from_shortnote(short_note)
		self.assertTrue(created_first > 0)

		# Second creation should detect existing cards and not duplicate
		created_second = create_flashcards_from_shortnote(short_note)
		self.assertEqual(created_second, 0)

	def test_share_token_public_access(self):
		from core.services.study_suite_service import generate_shortnotes_for_note
		short_note = generate_shortnotes_for_note(self.note)

		# Enable sharing
		post_resp = self.client.post(reverse("share_shortnote_toggle", args=[short_note.id]), {"action": "share"})
		self.assertEqual(post_resp.status_code, 200)

		short_note.refresh_from_db()
		self.assertIsNotNone(short_note.share_token)

		# Anonymous client can access via token
		anon_client = self.client_class()
		share_resp = anon_client.get(reverse("public_shortnote_view", args=[short_note.share_token]))
		self.assertEqual(share_resp.status_code, 200)
		self.assertContains(share_resp, "Shared Revision Guide")





