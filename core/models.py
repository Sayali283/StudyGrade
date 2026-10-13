import os
import uuid
import logging
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def note_upload_path(instance, filename):
    """
    Generates a secure, unpredictable file path to prevent path traversal
    and accidental file overwriting.
    """
    ext = os.path.splitext(filename)[1].lower()
    return f"notes/{uuid.uuid4().hex}{ext}"


class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    class_semester = models.CharField(max_length=20)

    def __str__(self):
        return self.user.username


class Parent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)

    def __str__(self):
        return self.user.username


class Notes(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100)
    file = models.FileField(upload_to=note_upload_path)
    file_size = models.PositiveBigIntegerField(default=0, help_text="Stored file size in bytes")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.subject


@receiver(post_delete, sender=Notes)
def auto_delete_file_on_note_delete(sender, instance, **kwargs):
    """Deletes underlying stored file when a note is removed from database."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except Exception as err:
            logger.warning("Failed to remove stored file for note %s: %s", instance.id, err)


class Quiz(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100)
    score = models.FloatField(default=0)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.subject} - {self.student.user.username}"


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    question_text = models.TextField()
    topic = models.CharField(max_length=100, default="General")

    option_a = models.CharField(max_length=255)
    option_b = models.CharField(max_length=255)
    option_c = models.CharField(max_length=255)
    option_d = models.CharField(max_length=255)

    correct_answer = models.CharField(max_length=255)
    explanation = models.TextField(blank=True, default="")
    difficulty = models.CharField(max_length=20, default="medium")
    source_reference = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    def __str__(self):
        return self.question_text[:50]


class QuestionAnswer(models.Model):
    question = models.OneToOneField(
        Question,
        on_delete=models.CASCADE,
        related_name="answer_record",
    )
    selected_answer = models.CharField(max_length=255, blank=True)
    is_correct = models.BooleanField(default=False)
    answered_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.question.topic}: {'correct' if self.is_correct else 'incorrect'}"


class QuestionReport(models.Model):
    """Allows students to flag questions for inaccuracies or ambiguity."""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="reports")
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report on Question #{self.question_id} by {self.student.user.username}"


class Flashcard(models.Model):
    note = models.ForeignKey(
        Notes,
        on_delete=models.CASCADE,
        related_name="flashcards",
    )
    front = models.TextField()
    back = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.front[:50]


class StudyDay(models.Model):
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="study_days",
    )
    study_date = models.DateField()

    class Meta:
        ordering = ["-study_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "study_date"],
                name="unique_student_study_day",
            ),
        ]

    def __str__(self):
        return f"{self.student} - {self.study_date}"

