"""
Authentication and Landing Views.
Handles student and parent registration, login, and session teardown.
"""
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages as dj_messages

from core.models import Student, Parent


def home(request):
    """Renders the public landing page."""
    return render(request, "home.html")


def student_signup(request):
    """Registers a new student account."""
    if request.method == "POST":
        try:
            name = (request.POST.get("name") or "").strip()
            email = (request.POST.get("email") or "").strip()
            password = request.POST.get("password")
            class_semester = (request.POST.get("class_semester") or "").strip()

            if not name or not email or not password or not class_semester:
                return render(request, "signup_student.html", {
                    "error": "All fields are required"
                })

            if User.objects.filter(username__iexact=email).exists():
                return render(request, "signup_student.html", {
                    "error": "An account with that email already exists"
                })

            user = User.objects.create_user(
                username=email,
                first_name=name,
                email=email,
                password=password
            )

            Student.objects.create(
                user=user,
                class_semester=class_semester
            )

            login(request, user)
            return redirect("student_dashboard")

        except Exception as e:
            return render(request, "signup_student.html", {
                "error": str(e)
            })

    return render(request, "signup_student.html")


def parent_signup(request):
    """Registers a parent account linked to a student."""
    if request.method == "POST":
        try:
            name = (request.POST.get("name") or "").strip()
            email = (request.POST.get("email") or "").strip()
            password = request.POST.get("password")
            student_email = (request.POST.get("student_email") or "").strip()

            if User.objects.filter(username__iexact=email).exists():
                dj_messages.error(request, "Email already registered")
                return redirect("parent_signup")

            try:
                student = Student.objects.get(user__email__iexact=student_email)
            except Student.DoesNotExist:
                dj_messages.error(request, "Student email not found. Please verify your child's registered email.")
                return redirect("parent_signup")

            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                password=password
            )

            Parent.objects.create(
                user=user,
                student=student
            )

            dj_messages.success(request, "Parent account created successfully. Please log in.")
            return redirect("login")

        except Exception as e:
            dj_messages.error(request, str(e))
            return redirect("parent_signup")

    return render(request, "signup_parent.html")


def user_login(request):
    """Authenticates student or parent and redirects to their respective dashboard."""
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password")

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if user is not None:
            login(request, user)
            next_url = request.GET.get("next") or request.POST.get("next")
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            if hasattr(user, "student"):
                return redirect("student_dashboard")
            elif hasattr(user, "parent"):
                return redirect("parent_dashboard")
            return redirect("home")
        else:
            dj_messages.error(request, "Invalid email or password")

    return render(request, "login.html")


def user_logout(request):
    """Logs out the authenticated user."""
    logout(request)
    return redirect("home")
