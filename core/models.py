from django.db import models
from django.contrib.auth.models import User

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
    file = models.FileField(upload_to="notes/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.subject


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
