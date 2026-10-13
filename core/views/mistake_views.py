"""
Mistake Notebook Views:
Displays collection of student struggles, filters, search, review priority,
practice-again launchers, and non-destructive removal from revision.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages as dj_messages
from django.http import JsonResponse, Http404

from core.models import Student, MistakeRecord, Notes, VisualFlowchart, ShortNote
from core.services.mistake_service import (
    get_student_mistakes,
    remove_mistake_from_revision,
    restore_mistake_to_revision,
    log_mistake_review,
)


@login_required
def mistake_notebook(request):
    """
    Main Mistake Notebook view:
    Lists mistakes with subject, topic, and status filters, search, and review priority sorting.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        if hasattr(request.user, "parent"):
            student = request.user.parent.student
        else:
            return redirect("login")

    subject_filter = request.GET.get("subject", "").strip()
    topic_filter = request.GET.get("topic", "").strip()
    status_filter = request.GET.get("status", "").strip()
    search_query = request.GET.get("q", "").strip()
    sort_by = request.GET.get("sort", "priority").strip()
    show_removed = request.GET.get("removed", "") == "1"

    mistakes = get_student_mistakes(
        student=student,
        subject=subject_filter,
        topic=topic_filter,
        status=status_filter,
        search_query=search_query,
        sort_by=sort_by,
        include_removed=show_removed,
    )

    all_student_mistakes = MistakeRecord.objects.filter(student=student)
    distinct_subjects = sorted(list(set(all_student_mistakes.values_list("subject", flat=True))))
    distinct_topics = sorted(list(set(all_student_mistakes.values_list("topic", flat=True))))

    unresolved_count = all_student_mistakes.filter(status="unresolved", is_in_revision=True).count()
    reviewing_count = all_student_mistakes.filter(status="reviewing", is_in_revision=True).count()
    mastered_count = all_student_mistakes.filter(status="mastered").count()
    total_active_count = all_student_mistakes.filter(is_in_revision=True).count()
    removed_count = all_student_mistakes.filter(is_in_revision=False).count()

    return render(request, "mistake_notebook.html", {
        "student": student,
        "mistakes": mistakes,
        "distinct_subjects": distinct_subjects,
        "distinct_topics": distinct_topics,
        "subject_filter": subject_filter,
        "topic_filter": topic_filter,
        "status_filter": status_filter,
        "search_query": search_query,
        "sort_by": sort_by,
        "show_removed": show_removed,
        "unresolved_count": unresolved_count,
        "reviewing_count": reviewing_count,
        "mastered_count": mastered_count,
        "total_active_count": total_active_count,
        "removed_count": removed_count,
    })


@login_required
def mistake_detail(request, mistake_id):
    """
    Shows full detail of a specific mistake, misconception takeaway,
    and links to connected visual diagrams, short notes, and practice.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        if hasattr(request.user, "parent"):
            student = request.user.parent.student
        else:
            return redirect("login")

    mistake = get_object_or_404(MistakeRecord, id=mistake_id, student=student)

    # Reading explanation logs review time without falsely awarding mastery
    if request.user == student.user:
        log_mistake_review(student, mistake.id, notes_read_only=True)

    # Connection D & E: Check for related diagrams or short notes
    related_diagram = VisualFlowchart.objects.filter(
        student=student,
        title__icontains=mistake.topic,
    ).first() or VisualFlowchart.objects.filter(
        note__subject__icontains=mistake.subject,
    ).first()

    related_note = ShortNote.objects.filter(
        student=student,
        title__icontains=mistake.topic,
    ).first() or ShortNote.objects.filter(
        note__subject__icontains=mistake.subject,
    ).first()

    source_note = Notes.objects.filter(
        student=student,
        subject__icontains=mistake.subject,
    ).first()

    return render(request, "mistake_detail.html", {
        "student": student,
        "mistake": mistake,
        "related_diagram": related_diagram,
        "related_note": related_note,
        "source_note": source_note,
    })


@login_required
@require_POST
def toggle_mistake_revision(request, mistake_id):
    """
    Removes or restores mistake to personal active revision list
    without deleting historical quiz records.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    mistake = get_object_or_404(MistakeRecord, id=mistake_id, student=student)
    action = request.POST.get("action", "toggle")

    if action == "restore" or (action == "toggle" and not mistake.is_in_revision):
        restore_mistake_to_revision(student, mistake.id)
        is_in_revision = True
        msg = "Mistake restored to active revision list."
    else:
        remove_mistake_from_revision(student, mistake.id)
        is_in_revision = False
        msg = "Mistake removed from active revision (quiz history preserved)."

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "success": True,
            "is_in_revision": is_in_revision,
            "message": msg,
        })

    dj_messages.success(request, msg)
    return redirect("mistake_notebook")
