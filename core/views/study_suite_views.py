"""
Study Suite Views:
Handles interactive Visual Flowcharts & Mind Maps (7 modes, editing, versions, node details, exports, test-me),
Cornell Notes & AI Cheat Sheets (7 modes, lengths, editing, interactive cue recall, flashcard creation),
and targeted Quiz Remediation.
"""
import uuid
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages as dj_messages
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone

from core.models import (
    Notes,
    Student,
    Quiz,
    Question,
    QuestionAnswer,
    VisualFlowchart,
    DiagramVersion,
    ShortNote,
    ShortNoteVersion,
    RemediationReview,
    MistakeRecord,
)
from core.services.study_suite_service import (
    generate_flowchart_for_note,
    generate_shortnotes_for_note,
    generate_quiz_remediation,
    validate_mermaid_syntax,
    generate_diagram_quiz,
    create_flashcards_from_shortnote,
    save_shortnote_version,
)
from core.services.streak_service import record_study_day
from core.services.spaced_repetition_service import schedule_concept_review


def _check_note_access(request, note):
    """Verifies that the logged in user is the owner student or linked parent."""
    if not note:
        return True
    if hasattr(request.user, "student") and note.student == request.user.student:
        return True
    if hasattr(request.user, "parent") and request.user.parent.student == note.student:
        return True
    return False


def _check_chart_access(request, chart):
    """Verifies diagram ownership."""
    if chart.student and hasattr(request.user, "student") and chart.student == request.user.student:
        return True
    if chart.note and _check_note_access(request, chart.note):
        return True
    return False


def _check_shortnote_access(request, short_note):
    """Verifies short note ownership."""
    if short_note.student and hasattr(request.user, "student") and short_note.student == request.user.student:
        return True
    if short_note.note and _check_note_access(request, short_note.note):
        return True
    return False


# ==============================================================================
# 1. Advanced Visual Flowcharts & Mindmaps Views
# ==============================================================================

@login_required
def note_flowchart(request, note_id):
    """
    Renders an interactive Mermaid.js diagram for the selected note.
    Supports 7 diagram types, complexity, explanation levels, node inspection, and versioning.
    """
    note = get_object_or_404(Notes, id=note_id)
    if not _check_note_access(request, note):
        raise Http404("You do not have permission to view this note's flowchart.")

    student = getattr(request.user, "student", None) or getattr(request.user, "parent", None).student

    diagram_type = request.GET.get("type", "flowchart").lower()
    valid_types = {"flowchart", "mindmap", "concept", "sequence", "timeline", "comparison", "hierarchy"}
    if diagram_type not in valid_types:
        diagram_type = "flowchart"

    complexity = request.GET.get("complexity", "balanced").lower()
    if complexity not in {"simple", "balanced", "detailed"}:
        complexity = "balanced"

    explanation_level = request.GET.get("level", "intermediate").lower()
    if explanation_level not in {"beginner", "intermediate", "advanced"}:
        explanation_level = "intermediate"

    force_refresh = request.GET.get("refresh") == "1"

    chart = generate_flowchart_for_note(
        note=note,
        diagram_type=diagram_type,
        complexity=complexity,
        explanation_level=explanation_level,
        force_refresh=force_refresh,
        student=student,
    )

    versions = chart.versions.all()[:10]
    related_mistakes = MistakeRecord.objects.filter(student=student, topic__icontains=note.subject, is_in_revision=True)

    return render(request, "note_flowchart.html", {
        "note": note,
        "chart": chart,
        "current_type": diagram_type,
        "current_complexity": complexity,
        "current_level": explanation_level,
        "versions": versions,
        "related_mistakes": related_mistakes,
        "node_details_json": json.dumps(chart.node_details or {}),
    })


@login_required
@require_POST
def save_flowchart_source(request, chart_id):
    """
    Safely saves edited Mermaid diagram syntax and title.
    Validates syntax, ensures security constraints, and saves a snapshot version.
    """
    chart = get_object_or_404(VisualFlowchart, id=chart_id)
    if not _check_chart_access(request, chart):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    new_title = (request.POST.get("title") or chart.title).strip()[:200]
    new_code = (request.POST.get("mermaid_code") or "").strip()

    is_valid, validation_msg = validate_mermaid_syntax(new_code)
    if not is_valid:
        return JsonResponse({"success": False, "error": validation_msg}, status=400)

    # Save snapshot version before replacing
    next_ver = chart.versions.count() + 1
    DiagramVersion.objects.create(
        flowchart=chart,
        title=chart.title,
        mermaid_code=chart.mermaid_code,
        node_details=chart.node_details,
        version_number=next_ver,
        change_summary=(request.POST.get("change_summary") or "Manual user edit")[:255],
    )

    chart.title = new_title
    chart.mermaid_code = new_code
    chart.save(update_fields=["title", "mermaid_code", "updated_at"])

    return JsonResponse({
        "success": True,
        "message": "Diagram successfully saved with new version snapshot!",
        "title": chart.title,
        "version_number": next_ver,
    })


@login_required
@require_POST
def restore_flowchart_version(request, chart_id, version_id):
    """Restores diagram to a previously saved version."""
    chart = get_object_or_404(VisualFlowchart, id=chart_id)
    if not _check_chart_access(request, chart):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    version = get_object_or_404(DiagramVersion, id=version_id, flowchart=chart)

    # Save current as a version before restoring
    DiagramVersion.objects.create(
        flowchart=chart,
        title=chart.title,
        mermaid_code=chart.mermaid_code,
        node_details=chart.node_details,
        version_number=chart.versions.count() + 1,
        change_summary=f"Snapshot before restoring v{version.version_number}",
    )

    chart.mermaid_code = version.mermaid_code
    chart.title = version.title
    if version.node_details:
        chart.node_details = version.node_details
    chart.save()

    dj_messages.success(request, f"Restored diagram to version #{version.version_number}.")
    return redirect("note_flowchart", note_id=chart.note_id)


@login_required
@require_POST
def duplicate_flowchart(request, chart_id):
    """Duplicates a diagram so the student can experiment freely."""
    original = get_object_or_404(VisualFlowchart, id=chart_id)
    if not _check_chart_access(request, original):
        raise Http404()

    clone = VisualFlowchart.objects.create(
        note=original.note,
        student=getattr(request.user, "student", None),
        title=f"Copy of {original.title}",
        diagram_type=original.diagram_type,
        complexity=original.complexity,
        explanation_level=original.explanation_level,
        mermaid_code=original.mermaid_code,
        node_details=original.node_details,
    )
    dj_messages.success(request, f"Created a duplicate diagram: '{clone.title}'")
    return redirect("note_flowchart", note_id=original.note_id)


@login_required
def diagram_test_me(request, chart_id):
    """
    'Test Me on This Diagram' (PART 4.6):
    Generates a learning exercise from the concepts in the diagram.
    Tracks answers and sends missed concepts directly to the Mistake Notebook!
    """
    chart = get_object_or_404(VisualFlowchart, id=chart_id)
    if not _check_chart_access(request, chart):
        raise Http404()

    student = getattr(request.user, "student", None) or getattr(request.user, "parent", None).student

    if request.method == "POST":
        # Evaluate student answers
        total = int(request.POST.get("total_questions", "0"))
        correct_count = 0
        mistakes_created = []

        for idx in range(total):
            q_text = request.POST.get(f"q_{idx}_text", "")
            ans_selected = request.POST.get(f"q_{idx}_selected", "").strip()
            ans_correct = request.POST.get(f"q_{idx}_correct", "").strip()
            topic = request.POST.get(f"q_{idx}_topic", chart.note.subject if chart.note else chart.title)
            expl = request.POST.get(f"q_{idx}_expl", "")

            if ans_selected and ans_selected.lower() == ans_correct.lower():
                correct_count += 1
            else:
                # Send incorrect concept to Mistake Notebook
                if q_text and ans_correct:
                    rec, _ = MistakeRecord.objects.get_or_create(
                        student=student,
                        question_text=q_text,
                        defaults={
                            "subject": chart.note.subject if chart.note else "Visual Learning",
                            "topic": topic,
                            "selected_answer": ans_selected or "None",
                            "correct_answer": ans_correct,
                            "explanation": expl,
                            "mistake_count": 1,
                            "status": "unresolved",
                            "is_in_revision": True,
                        },
                    )
                    mistakes_created.append(rec)

        score_pct = round((correct_count / total) * 100) if total else 0
        record_study_day(student)

        return render(request, "diagram_test_result.html", {
            "chart": chart,
            "correct_count": correct_count,
            "total": total,
            "score_pct": score_pct,
            "mistakes_created": mistakes_created,
        })

    # GET: Generate questions from diagram
    questions = generate_diagram_quiz(chart)

    return render(request, "diagram_test_me.html", {
        "chart": chart,
        "questions": questions,
        "total_questions": len(questions),
    })


# ==============================================================================
# 2. Cornell Short Notes & AI Cheat Sheets Views
# ==============================================================================

@login_required
def note_shortnotes(request, note_id):
    """
    Renders structured Cornell revision notes, executive summary,
    high-yield definitions, and memory mnemonics with mode and length controls.
    """
    note = get_object_or_404(Notes, id=note_id)
    if not _check_note_access(request, note):
        raise Http404("You do not have permission to view this note's revision guide.")

    student = getattr(request.user, "student", None) or getattr(request.user, "parent", None).student

    mode = request.GET.get("mode", "cornell").lower()
    valid_modes = {"quick", "cornell", "exam", "cheatsheet", "beginner", "interview", "custom"}
    if mode not in valid_modes:
        mode = "cornell"

    length_option = request.GET.get("length", "detailed").lower()
    if length_option not in {"very_short", "short", "detailed", "comprehensive"}:
        length_option = "detailed"

    explanation_level = request.GET.get("level", "intermediate").lower()
    if explanation_level not in {"beginner", "intermediate", "advanced"}:
        explanation_level = "intermediate"

    force_refresh = request.GET.get("refresh") == "1"

    short_note = generate_shortnotes_for_note(
        note=note,
        mode=mode,
        length_option=length_option,
        explanation_level=explanation_level,
        force_refresh=force_refresh,
        student=student,
    )

    # Track study time
    short_note.last_studied_at = timezone.now()
    short_note.save(update_fields=["last_studied_at"])

    versions = short_note.versions.all()[:8]

    return render(request, "note_shortnotes.html", {
        "note": note,
        "short_note": short_note,
        "current_mode": mode,
        "current_length": length_option,
        "current_level": explanation_level,
        "versions": versions,
    })


@login_required
@require_POST
def save_shortnotes_edit(request, short_note_id):
    """
    Safely saves personal edits, annotations, summary, cues, or definitions.
    Stores revision snapshot before updating.
    """
    short_note = get_object_or_404(ShortNote, id=short_note_id)
    if not _check_shortnote_access(request, short_note):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    # Save revision snapshot
    save_shortnote_version(short_note)

    new_title = (request.POST.get("title") or short_note.title).strip()[:200]
    new_summary = (request.POST.get("executive_summary") or short_note.executive_summary).strip()
    personal_notes = request.POST.get("personal_notes", short_note.personal_notes).strip()

    raw_cues = request.POST.get("cornell_cues")
    raw_defs = request.POST.get("key_definitions")
    raw_mnemonics = request.POST.get("mnemonics")

    short_note.title = new_title
    short_note.executive_summary = new_summary
    short_note.personal_notes = personal_notes

    if raw_cues:
        try:
            short_note.cornell_cues = json.loads(raw_cues)
        except Exception:
            pass

    if raw_defs:
        try:
            short_note.key_definitions = json.loads(raw_defs)
        except Exception:
            pass

    if raw_mnemonics:
        try:
            short_note.mnemonics = json.loads(raw_mnemonics)
        except Exception:
            pass

    short_note.save()

    return JsonResponse({
        "success": True,
        "message": "Short notes successfully updated with snapshot preserved!",
    })


@login_required
@require_POST
def restore_shortnotes_version(request, short_note_id, version_id):
    """Restores short notes to an earlier snapshot."""
    short_note = get_object_or_404(ShortNote, id=short_note_id)
    if not _check_shortnote_access(request, short_note):
        raise Http404()

    version = get_object_or_404(ShortNoteVersion, id=version_id, short_note=short_note)

    # Save snapshot before restoring
    save_shortnote_version(short_note)

    short_note.title = version.title
    short_note.executive_summary = version.executive_summary
    short_note.cornell_cues = version.cornell_cues
    short_note.key_definitions = version.key_definitions
    short_note.mnemonics = version.mnemonics
    short_note.save()

    dj_messages.success(request, "Restored notes to previous snapshot.")
    return redirect("note_shortnotes", note_id=short_note.note_id)


@login_required
def cornell_interactive_review(request, short_note_id):
    """
    Interactive Cornell Revision Mode (PART 5.6):
    Cues are shown first; student tries to answer from memory,
    reveals the note, marks confidence, and schedules spaced review!
    """
    short_note = get_object_or_404(ShortNote, id=short_note_id)
    if not _check_shortnote_access(request, short_note):
        raise Http404()

    cues = short_note.cornell_cues or []
    if not cues:
        dj_messages.info(request, "No cues available for this note. Please regenerate in Cornell mode.")
        return redirect("note_shortnotes", note_id=short_note.note_id)

    return render(request, "cornell_interactive.html", {
        "short_note": short_note,
        "note": short_note.note,
        "cues": cues,
        "cues_count": len(cues),
    })


@login_required
@require_POST
def create_flashcards_from_cues(request, short_note_id):
    """
    'Create Flashcards' action (PART 5.7):
    Generates Flashcard records from Cornell cues and definitions,
    reusing the existing flashcard system without duplicates.
    """
    short_note = get_object_or_404(ShortNote, id=short_note_id)
    if not _check_shortnote_access(request, short_note):
        raise Http404()

    if not short_note.note:
        dj_messages.error(request, "Cannot attach flashcards to standalone note.")
        return redirect("flashcard_home")

    created = create_flashcards_from_shortnote(short_note)
    if created > 0:
        dj_messages.success(request, f"Created {created} new flashcards from this note's cues & definitions!")
    else:
        dj_messages.info(request, "Flashcards for all cues in this note already exist.")

    return redirect("study_flashcards", note_id=short_note.note.id)


@login_required
@require_POST
def share_shortnote_toggle(request, short_note_id):
    """Generates or revokes explicit public share link for short note."""
    short_note = get_object_or_404(ShortNote, id=short_note_id)
    if not _check_shortnote_access(request, short_note):
        return JsonResponse({"error": "Unauthorized"}, status=403)

    action = request.POST.get("action", "share")
    if action == "revoke":
        short_note.share_token = None
        short_note.save(update_fields=["share_token"])
        return JsonResponse({"success": True, "shared": False})
    else:
        if not short_note.share_token:
            short_note.share_token = uuid.uuid4().hex
            short_note.save(update_fields=["share_token"])
        share_url = request.build_absolute_uri(f"/notes/shared/{short_note.share_token}/")
        return JsonResponse({"success": True, "shared": True, "share_url": share_url})


def public_shortnote_view(request, share_token):
    """Public read-only view for a note shared via explicit revocable token."""
    short_note = get_object_or_404(ShortNote, share_token=share_token)
    return render(request, "public_shortnote.html", {
        "short_note": short_note,
        "note": short_note.note,
    })


# ==============================================================================
# 3. Quiz Remediation Engine (Existing Feature Preserved)
# ==============================================================================

@login_required
def quiz_remediation(request, quiz_id):
    """
    Renders AI-powered remediation workout analyzing incorrect answers
    and offering targeted concept clarity with interactive mastery verification.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        if hasattr(request.user, "parent"):
            student = request.user.parent.student
        else:
            return redirect("login")

    quiz = get_object_or_404(Quiz, id=quiz_id, student=student)
    remediations = generate_quiz_remediation(quiz=quiz, student=student)

    resolved_count = sum(1 for r in remediations if r.is_resolved)
    total_count = len(remediations)

    return render(request, "quiz_remediation.html", {
        "quiz": quiz,
        "remediations": remediations,
        "resolved_count": resolved_count,
        "total_count": total_count,
    })


@login_required
@require_POST
def resolve_remediation(request, remediation_id):
    """
    AJAX endpoint: Evaluates student's answer to a remediation micro-practice item.
    """
    student = Student.objects.filter(user=request.user).first()
    if student is None:
        return JsonResponse({"error": "Unauthorized"}, status=401)

    remed = get_object_or_404(RemediationReview, id=remediation_id, student=student)
    selected_option = (request.POST.get("selected_option") or "").strip()

    is_correct = (selected_option == remed.correct_answer)
    if is_correct:
        remed.is_resolved = True
        remed.save(update_fields=["is_resolved"])

        # Also update connected MistakeRecord
        m = MistakeRecord.objects.filter(student=student, topic__icontains=remed.topic).first()
        if m:
            from core.services.mistake_service import log_mistake_review
            log_mistake_review(student, m.id, was_correct=True)

    return JsonResponse({
        "success": True,
        "is_correct": is_correct,
        "correct_answer": remed.correct_answer,
        "explanation": remed.explanation,
        "is_resolved": remed.is_resolved,
    })
