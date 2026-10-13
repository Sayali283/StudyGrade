"""
Study Suite Service:
Provides AI and heuristic generation for:
1. Interactive Visual Flowcharts & Mind Maps (Mermaid.js)
2. Cornell Notes & High-Yield Exam Cheat Sheets
3. Targeted Weak-Spot Quiz Remediation Engine
"""
import re
import json
import logging
from django.conf import settings
from google import genai
from decouple import config

from core.models import Notes, VisualFlowchart, ShortNote, RemediationReview, QuestionAnswer
from core.services.document_service import extract_document_text

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions & Syntax Sanitization
# ==============================================================================

def _clean_mermaid_code(code: str, diagram_type: str = "flowchart") -> str:
    """
    Cleans and sanitizes Mermaid syntax to prevent browser rendering errors.
    """
    # Remove markdown code block fences if present
    code = re.sub(r"^```(?:mermaid)?", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"```$", "", code.strip())
    code = code.strip()

    valid_starters = ("graph", "flowchart", "mindmap", "sequencediagram", "classdiagram")
    lower_code = code.lower()

    if not any(lower_code.startswith(starter) for starter in valid_starters):
        if diagram_type == "mindmap":
            code = f"mindmap\n  root((Concept Map))\n{code}"
        else:
            code = f"graph TD\n{code}"

    return code


def _sanitize_node_label(text: str, max_length: int = 40) -> str:
    """Sanitizes text for safe inclusion in a Mermaid node."""
    cleaned = re.sub(r'["\[\]\(\)\{\}\<\>]', "", text).strip()
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rsplit(" ", 1)[0] + "..."
    return cleaned or "Concept"


# ==============================================================================
# 1. Flowchart & Mindmap Generation
# ==============================================================================

def _fallback_flowchart(subject: str, text: str, diagram_type: str = "flowchart") -> str:
    """
    Rule-based NLP generator for Flowcharts and Mindmaps when Gemini is unreachable.
    Extracts key sentences and creates a clean, guaranteed-to-render Mermaid diagram.
    """
    safe_subject = _sanitize_node_label(subject, 35)

    # Extract informative sentences
    sentences = [
        s.strip() for s in re.split(r'[.\n]+', text)
        if len(s.strip()) > 15 and not s.strip().startswith(("#", "-", "*"))
    ][:8]

    if not sentences:
        sentences = [
            f"Core foundations of {safe_subject}",
            "Key principles and structures",
            "Functional interactions and rules",
            "Practical applications and exam takeaways",
        ]

    if diagram_type == "mindmap":
        lines = ["mindmap", f"  root(({safe_subject}))"]
        for idx, sentence in enumerate(sentences[:6], start=1):
            short_concept = _sanitize_node_label(sentence, 30)
            lines.append(f"    Branch_{idx}[{short_concept}]")
        return "\n".join(lines)

    elif diagram_type == "sequence":
        lines = ["graph LR", f'    Start(["Start: {safe_subject}"])']
        prev_node = "Start"
        for idx, sentence in enumerate(sentences[:5], start=1):
            node_id = f"Step{idx}"
            label = _sanitize_node_label(sentence, 35)
            lines.append(f'    {prev_node} --> {node_id}["{label}"]')
            prev_node = node_id
        lines.append(f'    {prev_node} --> Final(["Mastery: {safe_subject}"])')
        return "\n".join(lines)

    else:  # standard flowchart (graph TD)
        lines = [
            "graph TD",
            f'    Root(["{safe_subject}"])',
        ]
        for idx, sentence in enumerate(sentences[:6], start=1):
            node_id = f"Node{idx}"
            label = _sanitize_node_label(sentence, 35)
            lines.append(f'    Root --> {node_id}["{label}"]')
            # Add secondary sub-leaf for depth
            sub_id = f"Sub{idx}"
            lines.append(f'    {node_id} -.-> {sub_id}["Key Principle {idx}"]')
        return "\n".join(lines)


def generate_flowchart_for_note(note: Notes, diagram_type: str = "flowchart", force_refresh: bool = False) -> VisualFlowchart:
    """
    Generates an interactive Mermaid.js diagram from note text.
    Uses Gemini when configured, with robust NLP fallback.
    """
    if not force_refresh:
        existing = VisualFlowchart.objects.filter(note=note, diagram_type=diagram_type).first()
        if existing:
            return existing

    text = extract_document_text(note.file)
    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)

    mermaid_syntax = None

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
You are an expert educational visual architect. Analyze the study notes below and produce a clean, valid Mermaid.js diagram.
Diagram Type requested: {diagram_type}

RULES:
1. If diagram_type is 'flowchart', use 'graph TD' with informative nodes, showing relationships, causes, and workflows.
2. If diagram_type is 'mindmap', use 'mindmap' syntax with a root node and multi-level concept branches.
3. If diagram_type is 'sequence', use 'graph LR' showing progressive chronological steps from start to finish.
4. Wrap all node text in double quotes inside brackets, e.g.: NodeA["Clear Concept Description"].
5. Do NOT include markdown explanations or commentary. Return ONLY the raw Mermaid code block.
6. Ensure no syntax errors or unsupported characters in node IDs.

<STUDY_NOTES>
{text[:15000]}
</STUDY_NOTES>
"""
            models_to_try = [
                getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
                "gemini-3.8-flash",
                "gemini-2.5-flash",
            ]
            for model_name in models_to_try:
                try:
                    resp = client.models.generate_content(model=model_name, contents=prompt)
                    if resp and resp.text:
                        raw_code = resp.text.strip()
                        mermaid_syntax = _clean_mermaid_code(raw_code, diagram_type)
                        break
                except Exception as ex:
                    logger.warning("Flowchart generation failed on %s: %s", model_name, ex)
        except Exception as err:
            logger.warning("Gemini Flowchart call error: %s", err)

    if not mermaid_syntax:
        mermaid_syntax = _fallback_flowchart(note.subject, text, diagram_type)

    chart, _ = VisualFlowchart.objects.update_or_create(
        note=note,
        diagram_type=diagram_type,
        defaults={
            "title": f"{note.subject} {diagram_type.title()}",
            "mermaid_code": mermaid_syntax,
        },
    )
    return chart


# ==============================================================================
# 2. Cornell Short Notes & Cheat Sheet Generation
# ==============================================================================

def _fallback_shortnotes(subject: str, text: str) -> dict:
    """Heuristic fallback for Cornell notes and cheat sheet if offline."""
    clean_text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r'[.\n]+', clean_text) if len(s.strip()) > 20]

    # 1. Executive Summary
    summary = " ".join(sentences[:4]) if sentences else f"Overview notes for {subject} covering essential concepts."

    # 2. Key Definitions
    definitions = []
    def_patterns = [
        r"([A-Z][a-zA-Z\s]{2,25})\s+(?:is|are|refers to|means|defined as)\s+([^.]+)",
        r"([A-Z][a-zA-Z\s]{2,25}):\s+([^.]+)",
    ]
    for pattern in def_patterns:
        for match in re.finditer(pattern, text):
            term, defn = match.group(1).strip(), match.group(2).strip()
            if len(term) < 30 and len(defn) > 10 and len(definitions) < 6:
                definitions.append({"term": term, "definition": defn})

    if not definitions:
        words = re.findall(r"\b[A-Z][a-z]{3,15}\b", text)
        for w in list(dict.fromkeys(words))[:5]:
            definitions.append({
                "term": w,
                "definition": f"Core term and foundational concept within {subject} studies."
            })

    # 3. Cornell Cues
    cues = []
    for idx, sentence in enumerate(sentences[2:8], start=1):
        cues.append({
            "cue": f"Key question or cue #{idx}: What defines this aspect of {subject}?",
            "note": sentence,
        })
    if not cues:
        cues = [
            {"cue": f"What is the main goal of {subject}?", "note": "To master the fundamental theories and practical implementations."},
            {"cue": "How are components connected?", "note": "Through structured principles, properties, and analytical methods."},
        ]

    # 4. Mnemonics
    terms = [d["term"] for d in definitions[:4]]
    acronym = "".join([t[0].upper() for t in terms if t])
    mnemonics = [{
        "concept": f"Remembering Key Terms ({', '.join(terms)})",
        "mnemonic": acronym or "LEARN",
        "explanation": f"Use the acronym to rapidly recall key pillars of {subject} during revision.",
    }]

    return {
        "executive_summary": summary,
        "key_definitions": definitions,
        "cornell_cues": cues,
        "mnemonics": mnemonics,
    }


def generate_shortnotes_for_note(note: Notes, force_refresh: bool = False) -> ShortNote:
    """Generates Cornell Notes, Executive Summary, Definitions, and Mnemonics."""
    if not force_refresh:
        existing = ShortNote.objects.filter(note=note).first()
        if existing:
            return existing

    text = extract_document_text(note.file)
    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)

    notes_data = None

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
You are a master academic learning coach. Convert the following study notes into high-yield Cornell Revision Notes and an Exam Cheat Sheet.
Respond ONLY with a valid JSON object matching this exact structure:
{{
  "executive_summary": "Comprehensive 3-5 sentence high-yield summary of the document",
  "cornell_cues": [
    {{"cue": "Self-testing question or cue keyword", "note": "Clear, concise factual answer/notes for this cue"}}
  ],
  "key_definitions": [
    {{"term": "Vocabulary term, law, or formula", "definition": "Precise, memorable definition or formula explanation"}}
  ],
  "mnemonics": [
    {{"concept": "Topic or sequence to memorize", "mnemonic": "Acronym or memory phrase", "explanation": "Why this works to recall the concept"}}
  ]
}}

<STUDY_NOTES>
{text[:15000]}
</STUDY_NOTES>
"""
            models_to_try = [
                getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
                "gemini-3.8-flash",
                "gemini-2.5-flash",
            ]
            for model_name in models_to_try:
                try:
                    resp = client.models.generate_content(model=model_name, contents=prompt)
                    if resp and resp.text:
                        json_match = re.search(r"\{[\s\S]*\}", resp.text)
                        if json_match:
                            parsed = json.loads(json_match.group(0))
                            if "executive_summary" in parsed and "cornell_cues" in parsed:
                                notes_data = parsed
                                break
                except Exception as ex:
                    logger.warning("ShortNotes attempt failed on %s: %s", model_name, ex)
        except Exception as err:
            logger.warning("Gemini ShortNotes error: %s", err)

    if not notes_data:
        notes_data = _fallback_shortnotes(note.subject, text)

    short_note, _ = ShortNote.objects.update_or_create(
        note=note,
        defaults={
            "title": f"{note.subject} — Cornell Revision Guide",
            "executive_summary": notes_data.get("executive_summary", ""),
            "cornell_cues": notes_data.get("cornell_cues", []),
            "key_definitions": notes_data.get("key_definitions", []),
            "mnemonics": notes_data.get("mnemonics", []),
        },
    )
    return short_note


# ==============================================================================
# 3. Targeted Quiz Remediation Engine
# ==============================================================================

def generate_quiz_remediation(quiz, student) -> list[RemediationReview]:
    """
    Identifies all questions incorrectly answered in the quiz and produces
    targeted remediation guidance with interactive micro-practice.
    """
    existing_remediations = list(RemediationReview.objects.filter(quiz=quiz, student=student))
    if existing_remediations:
        return existing_remediations

    wrong_answers = (
        QuestionAnswer.objects.filter(question__quiz=quiz, is_correct=False)
        .select_related("question")
    )

    if not wrong_answers.exists():
        return []

    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)
    remediations = []

    for item in wrong_answers:
        q = item.question
        topic = q.topic or quiz.subject
        selected = item.selected_answer or "No answer provided"
        correct = q.correct_answer

        misconception = f"You selected '{selected}', while the correct answer is '{correct}'."
        key_takeaway = q.explanation or f"In {topic}, the correct concept requires: {correct}."
        practice_q = f"Check your understanding of {topic}: Which statement accurately describes {correct}?"
        practice_options = [
            f"It represents {correct} correctly.",
            f"It conflicts with {selected}.",
            f"It is unrelated to {topic}.",
            "None of the above.",
        ]
        practice_answer = f"It represents {correct} correctly."
        practice_expl = f"Remember: {correct} is the verified principle for {topic}."

        if api_key:
            try:
                client = genai.Client(api_key=api_key)
                prompt = f"""
A student made a mistake on this quiz question in topic '{topic}':
Question: {q.question_text}
Student's Incorrect Answer: {selected}
Correct Answer: {correct}
Existing Explanation: {q.explanation}

Provide a targeted learning remediation to fix this specific misconception.
Respond ONLY with a JSON object:
{{
  "misconception_analysis": "2-3 sentences explaining why a student might mistakenly choose '{selected}' and why '{correct}' is true",
  "key_takeaway": "1 memorable sentence rule to never miss this again",
  "practice_question": "A fresh single-choice verification question testing this exact rule",
  "practice_options": ["Option A", "Option B", "Option C", "Option D"],
  "correct_answer": "Option A",
  "explanation": "Why Option A is correct"
}}
"""
                resp = client.models.generate_content(
                    model=getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
                    contents=prompt,
                )
                if resp and resp.text:
                    match = re.search(r"\{[\s\S]*\}", resp.text)
                    if match:
                        data = json.loads(match.group(0))
                        misconception = data.get("misconception_analysis", misconception)
                        key_takeaway = data.get("key_takeaway", key_takeaway)
                        practice_q = data.get("practice_question", practice_q)
                        practice_options = data.get("practice_options", practice_options)
                        practice_answer = data.get("correct_answer", practice_answer)
                        practice_expl = data.get("explanation", practice_expl)
            except Exception as err:
                logger.warning("Remediation AI generation failed for question %s: %s", q.id, err)

        remed = RemediationReview.objects.create(
            quiz=quiz,
            student=student,
            topic=topic,
            misconception_analysis=misconception,
            key_takeaway=key_takeaway,
            practice_question=practice_q,
            practice_options=practice_options[:4],
            correct_answer=practice_answer,
            explanation=practice_expl,
            is_resolved=False,
        )
        remediations.append(remed)

    return remediations
