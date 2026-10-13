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
        ("mindmap", "Concept Mind Map"),
        ("concept", "Relationship Concept Map"),
        ("sequence", "Component Sequence Diagram"),
        ("timeline", "Chronological Timeline"),
        ("comparison", "Comparison Diagram"),
        ("hierarchy", "Classification & Hierarchy"),
    ]
    COMPLEXITY_CHOICES = [
        ("simple", "Simple"),
        ("balanced", "Balanced"),
        ("detailed", "Detailed"),
    ]
    LEVEL_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    note = models.ForeignKey(Notes, on_delete=models.CASCADE, related_name="flowcharts", null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="flowcharts", null=True, blank=True)
    title = models.CharField(max_length=200)
    diagram_type = models.CharField(max_length=50, default="flowchart", choices=DIAGRAM_TYPES)
    complexity = models.CharField(max_length=20, default="balanced", choices=COMPLEXITY_CHOICES)
    explanation_level = models.CharField(max_length=20, default="intermediate", choices=LEVEL_CHOICES)
    mermaid_code = models.TextField(help_text="Mermaid.js diagram syntax")
    node_details = models.JSONField(default=dict, blank=True, help_text="Metadata for interactive nodes: explanations, examples, references")
    is_favorite = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.note and not self.student:
            self.student = self.note.student
        super().save(*args, **kwargs)

    def __str__(self):
        subj = self.note.subject if self.note else "Standalone"
        return f"{subj} - {self.diagram_type} #{self.id}"


class DiagramVersion(models.Model):
    """Persists revision snapshots for VisualFlowchart before edits or regenerations."""
    flowchart = models.ForeignKey(VisualFlowchart, on_delete=models.CASCADE, related_name="versions")
    title = models.CharField(max_length=200)
    mermaid_code = models.TextField()
    node_details = models.JSONField(default=dict, blank=True)
    version_number = models.PositiveIntegerField(default=1)
    change_summary = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.flowchart.title} v{self.version_number}"


class ShortNote(models.Model):
    """Stores AI Cornell notes, executive summaries, key terms, and mnemonics."""
    MODE_CHOICES = [
        ("quick", "Quick Revision"),
        ("cornell", "Cornell Notes"),
        ("exam", "Exam Preparation"),
        ("cheatsheet", "Last-Minute Cheat Sheet"),
        ("beginner", "Beginner-Friendly Notes"),
        ("interview", "Interview Revision"),
        ("custom", "Custom Notes"),
    ]
    LENGTH_CHOICES = [
        ("very_short", "Very Short"),
        ("short", "Short"),
        ("detailed", "Detailed"),
        ("comprehensive", "Comprehensive"),
    ]
    LEVEL_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]

    note = models.ForeignKey(Notes, on_delete=models.CASCADE, related_name="short_notes", null=True, blank=True)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="short_notes", null=True, blank=True)
    title = models.CharField(max_length=200)
    mode = models.CharField(max_length=50, default="cornell", choices=MODE_CHOICES)
    length_option = models.CharField(max_length=20, default="detailed", choices=LENGTH_CHOICES)
    explanation_level = models.CharField(max_length=20, default="intermediate", choices=LEVEL_CHOICES)
    executive_summary = models.TextField(help_text="High-yield core summary")
    cornell_cues = models.JSONField(default=list, help_text="List of {cue: str, note: str}")
    key_definitions = models.JSONField(default=list, help_text="List of {term: str, definition: str}")
    mnemonics = models.JSONField(default=list, help_text="List of {concept: str, mnemonic: str, explanation: str}")
    personal_notes = models.TextField(blank=True, default="")
    tags = models.CharField(max_length=255, blank=True, default="")
    is_favorite = models.BooleanField(default=False)
    share_token = models.CharField(max_length=64, null=True, blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_studied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if self.note and not self.student:
            self.student = self.note.student
        super().save(*args, **kwargs)

    def __str__(self):
        subj = self.note.subject if self.note else "Study"
        return f"{subj} - Short Notes #{self.id}"


class ShortNoteVersion(models.Model):
    """Persists revision snapshots for ShortNote before edits or regenerations."""
    short_note = models.ForeignKey(ShortNote, on_delete=models.CASCADE, related_name="versions")
    title = models.CharField(max_length=200)
    executive_summary = models.TextField()
    cornell_cues = models.JSONField(default=list)
    key_definitions = models.JSONField(default=list)
    mnemonics = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.short_note.title} (Snapshot {self.id})"


class MistakeRecord(models.Model):
    """
    Personal collection of questions and concepts a student struggles with.
    Tracks repeated mistakes, resolution status, and review dates.
    """
    STATUS_CHOICES = [
        ("unresolved", "Unresolved"),
        ("reviewing", "In Review"),
        ("mastered", "Mastered"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="mistakes")
    question = models.ForeignKey(Question, on_delete=models.SET_NULL, null=True, blank=True, related_name="mistake_records")
    subject = models.CharField(max_length=100, db_index=True)
    topic = models.CharField(max_length=150, db_index=True)
    question_text = models.TextField()
    selected_answer = models.CharField(max_length=255, blank=True, default="")
    correct_answer = models.CharField(max_length=255)
    explanation = models.TextField(blank=True, default="")
    mistake_count = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, default="unresolved", choices=STATUS_CHOICES, db_index=True)
    is_in_revision = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Toggles active revision visibility without deleting quiz history",
    )
    first_missed_at = models.DateTimeField(auto_now_add=True)
    last_missed_at = models.DateTimeField(auto_now=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    next_review_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-mistake_count", "-last_missed_at"]

    def __str__(self):
        return f"{self.student.user.username} - {self.topic}: {self.question_text[:40]}"


class ScheduledReview(models.Model):
    """
    Spaced repetition scheduling for quiz mistakes, diagram concepts, short notes, and flashcards.
    Implements interval progression heuristics and prevents duplicate records for the same concept.
    """
    ITEM_TYPE_CHOICES = [
        ("mistake", "Quiz Mistake"),
        ("concept", "Diagram Concept"),
        ("note", "Cornell Note"),
        ("flashcard", "Flashcard"),
    ]
    STATUS_CHOICES = [
        ("due", "Due"),
        ("learning", "Learning"),
        ("mastered", "Mastered"),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="scheduled_reviews")
    item_type = models.CharField(max_length=30, choices=ITEM_TYPE_CHOICES, db_index=True)
    title = models.CharField(max_length=255)
    subject = models.CharField(max_length=100, db_index=True)
    topic = models.CharField(max_length=150, db_index=True)
    content_payload = models.JSONField(default=dict, blank=True)
    mistake_record = models.ForeignKey(MistakeRecord, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    note = models.ForeignKey(Notes, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    flowchart = models.ForeignKey(VisualFlowchart, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews")
    interval_days = models.FloatField(default=1.0)
    ease_factor = models.FloatField(default=2.5)
    review_count = models.PositiveIntegerField(default=0)
    consecutive_correct = models.PositiveIntegerField(default=0)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    next_review_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, default="due", choices=STATUS_CHOICES, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_review_date", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "item_type", "title", "topic"],
                name="unique_student_scheduled_review",
            )
        ]

    def __str__(self):
        return f"{self.student.user.username} - [{self.item_type}] {self.title} due {self.next_review_date}"


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


