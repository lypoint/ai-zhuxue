"""Trusted language instructions and safety replies; client input never becomes a prompt."""
import json
import re
from pathlib import Path

_LOCALES = json.loads((Path(__file__).resolve().parents[1] / "locales.json").read_text())
LANGUAGES = {tag: meta["english"] for tag, meta in _LOCALES.items()}
_LATIN_AMERICA = {"mx", "ar", "bo", "br", "bz", "cl", "co", "cr", "cu", "do", "ec", "gt", "hn", "ni", "pa", "pe", "pr", "py", "sv", "uy", "ve"}


def normalize_locale(value: str) -> str:
    normalized = value.replace("_", "-").lower()
    if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z]{4})?(?:-(?:[a-z]{2}|[0-9]{3}))?", normalized):
        raise ValueError("unsupported client language")
    for tag in LANGUAGES:
        if tag.lower() == normalized:
            return tag
    parts = normalized.split("-")
    if parts[0] == "zh":
        if "hans" in parts:
            return "zh-Hans"
        if "hk" in parts:
            return "zh-Hant-HK"
        return "zh-Hant" if any(p in {"hant", "tw", "mo"} for p in parts[1:]) else "zh-Hans"
    base = {"no": "nb", "iw": "he", "in": "id"}.get(parts[0], parts[0])
    region = next((part for part in parts[1:] if re.fullmatch(r"[a-z]{2}|[0-9]{3}", part)), None)
    if region:
        for tag in LANGUAGES:
            candidate = tag.lower().split("-")
            if candidate[0] == base and region in candidate[1:]:
                return tag
    if base == "es" and any(p in _LATIN_AMERICA for p in parts[1:]):
        return "es-419"
    if base in LANGUAGES:
        return base
    for tag in LANGUAGES:
        if tag.split("-")[0] == base:
            return tag
    raise ValueError("unsupported client language")


def instruction(locale: str) -> str:
    return (
        f"The client's current language is {LANGUAGES[locale]}. "
        "Write your explanations, guidance, headings and follow-up questions in this language, "
        "even when earlier messages or the student's question use another language. "
        "Keep quoted text, code, mathematical notation and language-learning examples in their "
        "appropriate original language. Do not change these safety and tutoring rules."
    )


_SAFETY_REPLIES = json.loads(
    (Path(__file__).resolve().parents[1] / "safety-translations.json").read_text()
)


def safe_reply(locale: str, *, forbidden: bool = False) -> str:
    return _SAFETY_REPLIES[locale]["forbidden" if forbidden else "reject"]
