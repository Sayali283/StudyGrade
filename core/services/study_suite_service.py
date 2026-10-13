"""
Study Suite Service:
Provides AI and heuristic generation for:
1. Interactive Visual Flowcharts & Mind Maps (Mermaid.js) with 7 Diagram Types, Node Details & Active Recall Quiz
2. Cornell Notes & High-Yield Exam Cheat Sheets
3. Targeted Weak-Spot Quiz Remediation Engine
"""
import re
import json
import logging
from django.conf import settings
from google import genai
from decouple import config

from core.models import (
    Notes,
    VisualFlowchart,
    DiagramVersion,
    ShortNote,
    ShortNoteVersion,
    RemediationReview,
    QuestionAnswer,
    Student,
)
from core.services.document_service import extract_document_text

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions, Syntax Sanitization & Security Validation
# ==============================================================================

def validate_mermaid_syntax(code: str) -> tuple[bool, str]:
    """
    Validates Mermaid.js syntax and checks security constraints.
    Prevents script injection, invalid headers, and unmatched brackets.
    """
    if not code or not code.strip():
        return False, "Diagram source cannot be empty."

    clean = code.strip()

    # Security check: disallow script tags, javascript: protocols, or inline event handlers
    if re.search(r"<\s*script|javascript:|onerror=|onload=|<\s*iframe", clean, re.IGNORECASE):
        return False, "Security violation: Diagram source contains disallowed executable HTML/scripts."

    lines = [line.strip() for line in clean.splitlines() if line.strip() and not line.strip().startswith("%%")]
    if not lines:
        return False, "Diagram contains no valid content lines."

    valid_starters = ("graph", "flowchart", "mindmap", "sequencediagram", "timeline", "classdiagram", "gantt")
    first_token = lines[0].lower().replace(" ", "")
    if not any(first_token.startswith(s) for s in valid_starters):
        return False, f"Invalid diagram header '{lines[0]}'. Must start with graph, flowchart, mindmap, sequenceDiagram, or timeline."

    # Verify matching bracket counts to avoid syntax crashes
    delimiters = [("(", ")"), ("[", "]"), ("{", "}")]
    for open_ch, close_ch in delimiters:
        if clean.count(open_ch) != clean.count(close_ch):
            return False, f"Unbalanced delimiter syntax: count of '{open_ch}' does not match '{close_ch}'."

    # Guard against oversized diagrams that crash rendering
    if len(lines) > 60:
        return False, "Diagram exceeds maximum allowed complexity (limit 60 lines)."

    return True, "Valid"


def _clean_mermaid_code(code: str, diagram_type: str = "flowchart") -> str:
    """
    Cleans markdown code fences and ensures proper start keywords.
    """
    code = re.sub(r"^```(?:mermaid)?", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"```$", "", code.strip())
    code = code.strip()

    # Sanitize any raw HTML tags to prevent XSS
    code = re.sub(r"<script[\s\S]*?</script>", "", code, flags=re.IGNORECASE)
    code = re.sub(r"<(?:iframe|embed|object)[^>]*>", "", code, flags=re.IGNORECASE)

    valid_starters = ("graph", "flowchart", "mindmap", "sequencediagram", "timeline", "classdiagram")
    lower_code = code.lower().replace(" ", "")

    if not any(lower_code.startswith(starter) for starter in valid_starters):
        if diagram_type == "mindmap":
            code = f"mindmap\n  root((Concept Map))\n{code}"
        elif diagram_type == "sequence":
            code = f"sequenceDiagram\n{code}"
        elif diagram_type == "timeline":
            code = f"timeline\n{code}"
        elif diagram_type in {"concept", "comparison"}:
            code = f"graph LR\n{code}"
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
# 1. Flowchart & Mindmap Generation (7 Supported Diagram Modes)
# ==============================================================================

def _fallback_diagram_with_details(
    subject: str,
    text: str,
    diagram_type: str = "flowchart",
    complexity: str = "balanced",
    explanation_level: str = "intermediate",
) -> tuple[str, dict]:
    """
    Deterministic rule-based generator for all 7 diagram modes when Gemini is offline.
    Extracts key sentences and creates a guaranteed-to-render diagram and rich node metadata.
    """
    safe_subject = _sanitize_node_label(subject, 35)

    sentences = [
        s.strip() for s in re.split(r'[.\n]+', text)
        if len(s.strip()) > 15 and not s.strip().startswith(("#", "-", "*"))
    ]

    count_map = {"simple": 4, "balanced": 6, "detailed": 9}
    node_count = count_map.get(complexity, 6)

    selected_sentences = sentences[:node_count] if sentences else [
        f"Core foundations of {safe_subject}",
        f"Key principles and structures in {safe_subject}",
        f"Functional interactions and rules of {safe_subject}",
        f"Practical implementations and use cases for {safe_subject}",
        f"Critical considerations and edge cases in {safe_subject}",
        f"Summary and exam takeaways for {safe_subject}",
    ][:node_count]

    node_details = {}

    if diagram_type == "mindmap":
        lines = ["mindmap", f"  root(({safe_subject}))"]
        for idx, sentence in enumerate(selected_sentences, start=1):
            short_concept = _sanitize_node_label(sentence, 30)
            lines.append(f"    Branch_{idx}[{short_concept}]")
            node_details[f"Branch_{idx}"] = {
                "name": short_concept,
                "simple_explanation": f"Foundational branch #{idx} of {safe_subject}.",
                "detailed_explanation": sentence,
                "example": f"Applied scenario covering {short_concept}.",
                "related_concepts": [safe_subject],
                "source_passage": sentence[:180],
            }
        mermaid_syntax = "\n".join(lines)

    elif diagram_type == "sequence":
        lines = [
            "sequenceDiagram",
            "    autonumber",
            f"    participant A as Student / Input",
            f"    participant B as {safe_subject} Engine",
            f"    participant C as Validation & Outcome",
        ]
        for idx, sentence in enumerate(selected_sentences[:5], start=1):
            label = _sanitize_node_label(sentence, 30)
            if idx % 2 == 1:
                lines.append(f"    A->>B: Step {idx}: {label}")
            else:
                lines.append(f"    B->>C: Process {idx}: {label}")
        lines.append(f"    C-->>A: Verified result for {safe_subject}")
        mermaid_syntax = "\n".join(lines)
        node_details["Sequence"] = {
            "name": f"{safe_subject} Lifecycle Sequence",
            "simple_explanation": f"Sequential progression through the phases of {safe_subject}.",
            "detailed_explanation": "Each message step depicts component interactions, requirements, and responses.",
            "example": "Standard operational workflow execution.",
            "related_concepts": [safe_subject],
            "source_passage": selected_sentences[0] if selected_sentences else "",
        }

    elif diagram_type == "timeline":
        lines = [
            "timeline",
            f"    title {safe_subject} Progression",
        ]
        for idx, sentence in enumerate(selected_sentences[:5], start=1):
            label = _sanitize_node_label(sentence, 30)
            lines.append(f"    Phase {idx} : {label} : Milestone {idx}")
            node_details[f"Phase {idx}"] = {
                "name": f"Phase {idx}: {label}",
                "simple_explanation": f"Timeline milestone in {safe_subject}.",
                "detailed_explanation": sentence,
                "example": f"Real-world historical or operational occurrence in Phase {idx}.",
                "related_concepts": [safe_subject],
                "source_passage": sentence[:180],
            }
        mermaid_syntax = "\n".join(lines)

    elif diagram_type == "concept":
        lines = ["graph LR", f'    Core(["{safe_subject}"])']
        for idx, sentence in enumerate(selected_sentences, start=1):
            node_id = f"Concept{idx}"
            label = _sanitize_node_label(sentence, 30)
            lines.append(f'    Core --> {node_id}["{label}"]')
            if idx > 1:
                lines.append(f'    Concept{idx-1} -.->|Relates to| {node_id}')
            node_details[label] = {
                "name": label,
                "simple_explanation": f"Key concept connected to {safe_subject}.",
                "detailed_explanation": sentence,
                "example": f"Illustrative concept connection within {safe_subject}.",
                "related_concepts": [safe_subject],
                "source_passage": sentence[:180],
            }
        mermaid_syntax = "\n".join(lines)

    elif diagram_type == "comparison":
        lines = [
            "graph TB",
            f'    Root(["{safe_subject}: Comparative Analysis"])',
            '    subgraph Core Dimensions',
        ]
        for idx, sentence in enumerate(selected_sentences[:4], start=1):
            label = _sanitize_node_label(sentence, 30)
            lines.append(f'        CompA{idx}["Factor {idx}: {label}"]')
            node_details[f"Factor {idx}"] = {
                "name": label,
                "simple_explanation": f"Comparative dimension #{idx}.",
                "detailed_explanation": sentence,
                "example": f"Exam scenario contrasting {label}.",
                "related_concepts": [safe_subject],
                "source_passage": sentence[:180],
            }
        lines.append('    end')
        lines.append('    Root --> CompA1')
        mermaid_syntax = "\n".join(lines)

    elif diagram_type == "hierarchy":
        lines = [
            "graph TD",
            f'    Root(["{safe_subject} Domain"])',
            '    Root --> BranchA["Foundations"]',
            '    Root --> BranchB["Applications"]',
        ]
        for idx, sentence in enumerate(selected_sentences[:4], start=1):
            label = _sanitize_node_label(sentence, 28)
            parent = "BranchA" if idx <= 2 else "BranchB"
            lines.append(f'    {parent} --> Item{idx}["{label}"]')
            node_details[label] = {
                "name": label,
                "simple_explanation": f"Hierarchical sub-classification under {parent}.",
                "detailed_explanation": sentence,
                "example": f"Structural classification example of {label}.",
                "related_concepts": [safe_subject, parent],
                "source_passage": sentence[:180],
            }
        mermaid_syntax = "\n".join(lines)

    else:  # default 'flowchart' (graph TD)
        lines = [
            "graph TD",
            f'    Root(["{safe_subject}"])',
        ]
        for idx, sentence in enumerate(selected_sentences, start=1):
            node_id = f"Node{idx}"
            label = _sanitize_node_label(sentence, 35)
            lines.append(f'    Root --> {node_id}["{label}"]')
            sub_id = f"Sub{idx}"
            lines.append(f'    {node_id} -.-> {sub_id}["Key Principle {idx}"]')
            node_details[label] = {
                "name": label,
                "simple_explanation": f"Core component of {safe_subject}.",
                "detailed_explanation": sentence,
                "example": f"Practical application demonstrating {label}.",
                "related_concepts": [safe_subject],
                "source_passage": sentence[:180],
            }
        mermaid_syntax = "\n".join(lines)

    return mermaid_syntax, node_details


def generate_flowchart_for_note(
    note: Notes,
    diagram_type: str = "flowchart",
    complexity: str = "balanced",
    explanation_level: str = "intermediate",
    force_refresh: bool = False,
    student: Student | None = None,
) -> VisualFlowchart:
    """
    Generates an interactive Mermaid.js diagram and detailed node metadata.
    Supports all 7 educational diagram types with complexity & explanation levels.
    """
    valid_types = {"flowchart", "mindmap", "concept", "sequence", "timeline", "comparison", "hierarchy"}
    if diagram_type not in valid_types:
        diagram_type = "flowchart"

    student = student or (note.student if note else None)

    if not force_refresh:
        existing = VisualFlowchart.objects.filter(
            note=note,
            diagram_type=diagram_type,
            complexity=complexity,
            explanation_level=explanation_level,
        ).first()
        if existing and existing.mermaid_code:
            return existing

    text = extract_document_text(note.file) if note and note.file else ""
    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)

    mermaid_syntax = None
    node_details = {}

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
You are an expert educational visual architect and learning design engineer.
Analyze the study notes below and produce a clean, valid Mermaid.js diagram AND node metadata for active learning.

Diagram Type requested: {diagram_type}
Complexity requested: {complexity} (simple: 4-6 nodes, balanced: 7-12 nodes, detailed: 13-18 nodes)
Explanation Level: {explanation_level} (beginner, intermediate, advanced)

CRITICAL RULES:
1. Return ONLY a valid JSON object matching this schema:
{{
  "mermaid_code": "graph TD or mindmap or sequenceDiagram syntax...",
  "node_details": {{
    "Node Concept Name": {{
      "name": "Node Concept Name",
      "simple_explanation": "1-2 sentence intuitive explanation",
      "detailed_explanation": "In-depth educational explanation",
      "example": "Real-world or exam example",
      "related_concepts": ["Concept 1", "Concept 2"],
      "source_passage": "Relevant quote from text if present"
    }}
  }}
}}
2. Syntax conventions by diagram_type:
   - 'flowchart': graph TD with decision points and process flows
   - 'mindmap': mindmap with root node and nested concept branches
   - 'concept': graph LR with annotated relationship arrows (-- Relates to -->)
   - 'sequence': sequenceDiagram with participants and chronological messages
   - 'timeline': timeline with title and periodic milestones
   - 'comparison': graph TB comparing concepts via subgraphs
   - 'hierarchy': graph TD showing parent-child taxonomies
3. Keep all node labels clean and wrapped in quotes. Do not include markdown fences outside the JSON.
4. Bound total nodes to at most 18. Never generate gigantic unreadable diagrams.

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
                            candidate_code = parsed.get("mermaid_code", "")
                            cleaned = _clean_mermaid_code(candidate_code, diagram_type)
                            is_valid, _ = validate_mermaid_syntax(cleaned)
                            if is_valid:
                                mermaid_syntax = cleaned
                                node_details = parsed.get("node_details", {})
                                break
                except Exception as ex:
                    logger.warning("Diagram generation failed on %s: %s", model_name, ex)
        except Exception as err:
            logger.warning("Gemini diagram call error: %s", err)

    if not mermaid_syntax:
        mermaid_syntax, node_details = _fallback_diagram_with_details(
            subject=note.subject if note else "Study Topic",
            text=text,
            diagram_type=diagram_type,
            complexity=complexity,
            explanation_level=explanation_level,
        )

    # Persist or update the diagram record
    chart, created = VisualFlowchart.objects.update_or_create(
        note=note,
        diagram_type=diagram_type,
        defaults={
            "student": student,
            "title": f"{note.subject if note else 'Study'} {diagram_type.title()}",
            "complexity": complexity,
            "explanation_level": explanation_level,
            "mermaid_code": mermaid_syntax,
            "node_details": node_details,
        },
    )

    # Save initial version snapshot if created or refreshed
    if not DiagramVersion.objects.filter(flowchart=chart).exists():
        DiagramVersion.objects.create(
            flowchart=chart,
            title=chart.title,
            mermaid_code=chart.mermaid_code,
            node_details=chart.node_details,
            version_number=1,
            change_summary="Initial AI generation",
        )

    return chart


def generate_diagram_quiz(flowchart: VisualFlowchart) -> list[dict]:
    """
    Generates a 3-5 question learning check from the concepts in the diagram
    for the 'Test Me on This Diagram' active learning mode.
    """
    node_names = list(flowchart.node_details.keys()) if flowchart.node_details else []
    if not node_names:
        # Extract from mermaid code
        raw_nodes = re.findall(r'\["([^"]+)"\]|\(\("([^"]+)"\)\)', flowchart.mermaid_code)
        node_names = [n[0] or n[1] for n in raw_nodes if (n[0] or n[1])]

    subject = flowchart.note.subject if flowchart.note else flowchart.title
    questions = []

    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)

    if api_key and len(flowchart.mermaid_code) > 20:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
You are an expert tutor creating a concept verification quiz based directly on this diagram.
Diagram Type: {flowchart.diagram_type}
Subject: {subject}

Diagram Syntax:
{flowchart.mermaid_code}

Generate exactly 3 multiple-choice questions that test whether a student understands the relationships, steps, or concepts shown in this diagram.
Return ONLY a valid JSON array of objects:
[
  {{
    "question": "Clear concept inquiry based on diagram relationship",
    "topic": "{subject}",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": "Option A",
    "explanation": "Why Option A is correct according to the diagram",
    "difficulty": "medium"
  }}
]
"""
            resp = client.models.generate_content(
                model=getattr(settings, "GEMINI_MODEL", "gemini-3.5-flash-lite"),
                contents=prompt,
            )
            if resp and resp.text:
                json_match = re.search(r"\[[\s\S]*\]", resp.text)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        questions = parsed[:5]
        except Exception as err:
            logger.warning("Diagram quiz generation via AI failed: %s", err)

    if not questions:
        # Fallback question generation grounded in diagram nodes
        names = node_names if len(node_names) >= 4 else [
            f"{subject} Foundation",
            f"{subject} Mechanism",
            f"{subject} Output",
            f"{subject} Regulation",
        ]
        for idx in range(min(3, len(names))):
            target = names[idx]
            other = [n for n in names if n != target]
            distractors = other[:3] if len(other) >= 3 else ["Alternative Process", "Inverted Flow", "External Variable"]
            options = [target] + distractors[:3]
            import random
            random.shuffle(options)

            questions.append({
                "question": f"In the visual breakdown of '{subject}', which element represents '{target}'?",
                "topic": subject,
                "options": options,
                "answer": target,
                "explanation": f"According to the diagram, '{target}' is a verified concept within {subject}.",
                "difficulty": "medium",
            })

    return questions


# ==============================================================================
# 2. Cornell Short Notes & Cheat Sheet Generation
# ==============================================================================

def _fallback_shortnotes(subject: str, text: str) -> dict:
    """Heuristic fallback for Cornell notes and cheat sheet if offline."""
    clean_text = re.sub(r"\s+", " ", text).strip()
    sentences = [s.strip() for s in re.split(r'[.\n]+', clean_text) if len(s.strip()) > 20]

    summary = " ".join(sentences[:4]) if sentences else f"Overview notes for {subject} covering essential concepts."

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

    if not definitions and sentences:
        for s in sentences[:3]:
            words = s.split()
            if len(words) >= 4:
                definitions.append({
                    "term": " ".join(words[:2]),
                    "definition": s,
                })

    cues = []
    for idx, sentence in enumerate(sentences[2:8], start=1):
        cues.append({
            "cue": f"Key question #{idx}: What defines this aspect of {subject}?",
            "note": sentence,
        })
    if not cues:
        cues = [
            {"cue": f"What is the main goal of {subject}?", "note": "To master the fundamental theories and practical implementations."},
            {"cue": "How are components connected?", "note": "Through structured principles, properties, and analytical methods."},
        ]

    terms = [d["term"] for d in definitions[:4]]
    acronym = "".join([t[0].upper() for t in terms if t and t[0].isalpha()])
    mnemonics = [{
        "concept": f"Remembering Key Terms ({', '.join(terms)})" if terms else f"Core Pillars of {subject}",
        "mnemonic": acronym if len(acronym) >= 2 else "CORE",
        "explanation": f"Use this acronym to rapidly recall key pillars of {subject} during revision.",
    }]

    return {
        "executive_summary": summary,
        "key_definitions": definitions,
        "cornell_cues": cues,
        "mnemonics": mnemonics,
    }


def generate_shortnotes_for_note(
    note: Notes,
    mode: str = "cornell",
    length_option: str = "detailed",
    explanation_level: str = "intermediate",
    force_refresh: bool = False,
    student: Student | None = None,
) -> ShortNote:
    """
    Generates Cornell Notes, Executive Summary, Definitions, and Mnemonics
    with configurable modes (Quick, Cornell, Exam, Cheat Sheet, Beginner, Interview, Custom).
    """
    student = student or (note.student if note else None)

    if not force_refresh:
        existing = ShortNote.objects.filter(note=note, mode=mode).first()
        if existing and existing.executive_summary:
            return existing

    text = extract_document_text(note.file) if note and note.file else ""
    api_key = config("GEMINI_API_KEY", default=None) or getattr(settings, "GEMINI_API_KEY", None)

    notes_data = None

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
You are a master academic learning coach and educational author.
Convert the study notes below into high-yield Cornell Revision Notes and an Exam Cheat Sheet.

Requested Mode: {mode} (options: quick, cornell, exam, cheatsheet, beginner, interview, custom)
Requested Length: {length_option} (very_short, short, detailed, comprehensive)
Explanation Level: {explanation_level} (beginner, intermediate, advanced)

EDUCATIONAL QUALITY RULES:
1. Extract DEFINITIONS only from true definitions stated in the source. Do NOT invent arbitrary definitions.
2. Form MNEMONICS only when they meaningfully help remember a list, sequence, or rule. Verify that the acronym letters match the concepts!
3. Ground all content strictly in the study notes. Clearly distinguish source facts from general context.
4. Respond ONLY with a valid JSON object matching this exact structure:
{{
  "executive_summary": "Comprehensive high-yield summary tailored to the requested mode and length",
  "cornell_cues": [
    {{"cue": "Active recall self-testing question or cue keyword", "note": "Clear, accurate factual explanation grounded in text"}}
  ],
  "key_definitions": [
    {{"term": "Vocabulary term, law, or formula", "definition": "Precise definition or formula explanation"}}
  ],
  "mnemonics": [
    {{"concept": "Topic or sequence to memorize", "mnemonic": "Acronym or memory phrase", "explanation": "Step-by-step breakdown of how the letters map to the concepts"}}
  ]
}}

<STUDY_NOTES>
{text[:16000]}
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
        notes_data = _fallback_shortnotes(note.subject if note else "Study Topic", text)

    mode_titles = {
        "quick": "Quick Revision Summary",
        "cornell": "Cornell Active Recall Notes",
        "exam": "Exam High-Yield Preparation Guide",
        "cheatsheet": "Last-Minute Cheat Sheet",
        "beginner": "Beginner-Friendly Study Guide",
        "interview": "Technical Interview Revision",
        "custom": "Personalized Revision Guide",
    }
    title_suffix = mode_titles.get(mode, "Cornell Revision Guide")

    short_note, _ = ShortNote.objects.update_or_create(
        note=note,
        mode=mode,
        defaults={
            "student": student,
            "title": f"{note.subject if note else 'Study'} — {title_suffix}",
            "length_option": length_option,
            "explanation_level": explanation_level,
            "executive_summary": notes_data.get("executive_summary", ""),
            "cornell_cues": notes_data.get("cornell_cues", []),
            "key_definitions": notes_data.get("key_definitions", []),
            "mnemonics": notes_data.get("mnemonics", []),
        },
    )

    # Save initial version snapshot
    if not short_note.versions.exists():
        ShortNoteVersion.objects.create(
            short_note=short_note,
            title=short_note.title,
            executive_summary=short_note.executive_summary,
            cornell_cues=short_note.cornell_cues,
            key_definitions=short_note.key_definitions,
            mnemonics=short_note.mnemonics,
        )

    return short_note


def create_flashcards_from_shortnote(short_note: ShortNote, selected_cues: list[int] | None = None) -> int:
    """
    Transforms Cornell cues and key definitions from a short note into interactive Flashcards.
    Prevents duplicate flashcards.
    """
    from core.models import Flashcard
    if not short_note.note:
        return 0

    note = short_note.note
    created_count = 0

    # 1. Process cues
    cues = short_note.cornell_cues or []
    for idx, item in enumerate(cues):
        if selected_cues is not None and idx not in selected_cues:
            continue
        front = item.get("cue", "").strip()
        back = item.get("note", "").strip()
        if front and back:
            # Check for existing duplicate front
            if not Flashcard.objects.filter(note=note, front=front).exists():
                Flashcard.objects.create(note=note, front=front, back=back)
                created_count += 1

    # 2. Process definitions if no selective cue index filtering
    if selected_cues is None:
        definitions = short_note.key_definitions or []
        for d in definitions:
            term = d.get("term", "").strip()
            defn = d.get("definition", "").strip()
            if term and defn:
                front = f"Definition: What is {term}?"
                if not Flashcard.objects.filter(note=note, front=front).exists():
                    Flashcard.objects.create(note=note, front=front, back=defn)
                    created_count += 1

    return created_count


def save_shortnote_version(short_note: ShortNote) -> ShortNoteVersion:
    """Creates a snapshot before manual modifications or regenerations."""
    return ShortNoteVersion.objects.create(
        short_note=short_note,
        title=short_note.title,
        executive_summary=short_note.executive_summary,
        cornell_cues=short_note.cornell_cues,
        key_definitions=short_note.key_definitions,
        mnemonics=short_note.mnemonics,
    )



# ==============================================================================
# 3. Targeted Quiz Remediation Engine (Connected with Mistake Notebook)
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
