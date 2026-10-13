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


class VisualFlowchart(models.Model):
    """Stores AI-generated visual flowcharts and mindmaps for study notes."""
    DIAGRAM_TYPES = [
        ("flowchart", "Process Flowchart"),
        ("mindmap", "Mind Map"),
        ("sequence", "Chronological Timeline"),
    ]

    note = models.ForeignKey(Notes, on_delete=models.CASCADE, related_name="flowcharts")
    title = models.CharField(max_length=200)
    diagram_type = models.CharField(max_length=50, default="flowchart", choices=DIAGRAM_TYPES)
    mermaid_code = models.TextField(help_text="Mermaid.js diagram syntax")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.note.subject} - {self.diagram_type} #{self.id}"


class ShortNote(models.Model):
    """Stores AI Cornell notes, executive summaries, key terms, and mnemonics."""
    note = models.ForeignKey(Notes, on_delete=models.CASCADE, related_name="short_notes")
    title = models.CharField(max_length=200)
    executive_summary = models.TextField(help_text="High-yield core summary")
    cornell_cues = models.JSONField(default=list, help_text="List of {cue: str, note: str}")
    key_definitions = models.JSONField(default=list, help_text="List of {term: str, definition: str}")
    mnemonics = models.JSONField(default=list, help_text="List of {concept: str, mnemonic: str, explanation: str}")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.note.subject} - Short Notes #{self.id}"


class RemediationReview(models.Model):
    """Personalized remediation guidance for weak spots identified in completed quizzes."""
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="remediations")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="remediations")
    topic = models.CharField(max_length=150)
    misconception_analysis = models.TextField()
    key_takeaway = models.TextField()
    practice_question = models.TextField()
    practice_options = models.JSONField(default=list)
    correct_answer = models.CharField(max_length=255)
    explanation = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Remediation: {self.topic} for {self.student.user.username}"

