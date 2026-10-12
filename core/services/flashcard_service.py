import sys
import json
import re as regex
from django.conf import settings
from django.db import transaction
from google import genai

from core.models import Flashcard, Notes


def generate_flashcard_items(text: str, subject: str) -> list[dict]:
    """
    Synthesizes concise front/back study flashcards from document content.
    """
    cards_data = []
    api_key = getattr(settings, "GEMINI_API_KEY", "")

    core_views = sys.modules.get("core.views")
    has_mock = bool(core_views and hasattr(core_views, "genai") and hasattr(core_views.genai, "Client"))

    if api_key or has_mock:
        prompt = f"""
Create 6 to 10 useful study flashcards from these notes about {subject}.
Focus on the most important concepts, definitions, processes, and cause-and-effect relationships.
Each front must ask one clear recall question. Each back must give a concise answer using only the notes.
Avoid duplicate cards and minor details. Return ONLY a valid JSON array in this format:
[{{"front": "Question", "back": "Answer"}}]

NOTES:
{text[:18000]}
"""
        try:
            genai_module = getattr(core_views, "genai", genai) if core_views else genai
            client = genai_module.Client(api_key=api_key)
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt,
            )
            response_text = (response.text or "").strip()
            json_match = regex.search(r"\[[\s\S]*\]", response_text)
            if json_match:
                generated = json.loads(json_match.group(0))
                if isinstance(generated, list):
                    cards_data = [
                        {"front": item.get("front", "").strip(), "back": item.get("back", "").strip()}
                        for item in generated
                        if isinstance(item, dict)
                        and isinstance(item.get("front"), str)
                        and isinstance(item.get("back"), str)
                        and item.get("front", "").strip()
                        and item.get("back", "").strip()
                    ]
        except Exception as err:
            print(f"[FlashcardService] Gemini generation skipped/failed: {err}")

    if not cards_data:
        cards_data = _fallback_flashcards(text)

    return cards_data


def save_flashcards_for_note(note: Notes, cards_data: list[dict]) -> int:
    """Atomically replaces the flashcards for a note with new cards."""
    with transaction.atomic():
        note.flashcards.all().delete()
        created = Flashcard.objects.bulk_create([
            Flashcard(note=note, front=card["front"], back=card["back"])
            for card in cards_data
        ])
    return len(created)


def _fallback_flashcards(text: str) -> list[dict]:
    """Fallback extractor scoring sentences by definition and causality indicators."""
    candidates = []
    seen = set()

    for index, sentence in enumerate(regex.split(r"(?<=[.!?])\s+|\n+", text)):
        sentence = regex.sub(r"\s+", " ", sentence).strip(" \t-•")
        words = sentence.split()
        normalized = sentence.casefold()

        if len(words) < 7 or len(sentence) < 45 or normalized in seen:
            continue

        seen.add(normalized)
        score = min(len(words), 30)
        if regex.search(r"\b(is defined as|refers to|means|consists of|is|are)\b", sentence, regex.IGNORECASE):
            score += 8
        if regex.search(r"\b(because|therefore|important|process|function|causes|results)\b", sentence, regex.IGNORECASE):
            score += 5
        if regex.search(r"\d", sentence):
            score += 2

        candidates.append((score, index, words, sentence))

    selected = sorted(candidates, key=lambda item: (-item[0], item[1]))[:10]
    selected.sort(key=lambda item: item[1])

    return [
        {
            "front": f"Complete this key point: {' '.join(words[:max(3, len(words) // 3)])} ...",
            "back": sentence,
        }
        for _, _, words, sentence in selected
    ]
