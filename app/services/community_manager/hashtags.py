"""Service de selection des hashtags pour les publications du Community Manager IA."""

import json
from typing import Any

DEFAULT_MAX_HASHTAGS = 5

HASHTAG_LIBRARY: list[dict[str, str]] = [
    {"name": "#trailrunning", "category": "discipline"},
    {"name": "#trailrunner", "category": "discipline"},
    {"name": "#runningfrance", "category": "discipline"},
    {"name": "#mountainrunning", "category": "discipline"},
    {"name": "#ultratrail", "category": "ultra_endurance"},
    {"name": "#ultrarunning", "category": "ultra_endurance"},
    {"name": "#endurancerunning", "category": "ultra_endurance"},
    {"name": "#trailaddict", "category": "ultra_endurance"},
    {"name": "#verticalrunning", "category": "mountain"},
    {"name": "#denivele", "category": "mountain"},
    {"name": "#naturetrail", "category": "discovery"},
    {"name": "#foresttrail", "category": "discovery"},
    {"name": "#jepepagtrail", "category": "identity"},
]

DEFAULT_BRAND_HASHTAG = "#jepepagtrail"


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return text.strip("#").strip()


def normalize_hashtag_list(value: Any) -> list[str]:
    """Normalise une valeur (str JSON, liste ou str brute) en liste de hashtags."""
    if not value:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("#"):
            return []
        return [h.strip() for h in text.split() if h.strip().startswith("#")]
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            h = str(item or "").strip()
            if h.startswith("#"):
                result.append(h)
        return result
    return []


def _json_dumps(names: list[str]) -> str:
    return json.dumps(names)


def hashtags_to_str(hashtags: Any) -> str:
    """Convertit une liste/str de hashtags en JSON."""
    names = normalize_hashtag_list(hashtags)
    if not names:
        return "[]"
    return _json_dumps(names)


def build_hashtag_candidates(context: dict[str, Any], strategy: dict[str, Any]) -> list[str]:
    """Construit les hashtags candidats selon le contexte et la strategie."""
    context_text = " ".join(
        str(context.get(key) or "") for key in ("topic", "notes", "activity_name", "sport_type", "title")
    ).lower()
    candidates: list[str] = []

    brand = str(strategy.get("signature_hashtag") or DEFAULT_BRAND_HASHTAG)
    candidates.append("#" + brand.lstrip("#"))

    for item in HASHTAG_LIBRARY:
        name = item["name"]
        key = name.lstrip("#").lower()
        if key == "jepepagtrail":
            continue
        candidates.append(name)

    unique: list[str] = []
    seen: set[str] = set()
    for h in candidates:
        key = h.lstrip("#").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(h)
    return unique


def select_hashtags(
    context: dict[str, Any],
    strategy: dict[str, Any],
    existing: list[str] | None = None,
    max_hashtags: int | None = None,
) -> list[str]:
    """Selectionne jusqu'a max_hashtags (5 par defaut) les hashtags pertinents."""
    strategy_max = strategy.get("max_hashtags") if isinstance(strategy.get("max_hashtags"), int) else None
    limit = max_hashtags if isinstance(max_hashtags, int) and max_hashtags >= 1 else (strategy_max or DEFAULT_MAX_HASHTAGS)
    existing_norm = {str(h).lstrip("#").lower() for h in (existing or []) if str(h).startswith("#")}
    candidates = build_hashtag_candidates(context, strategy)

    selected: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        name = candidate if candidate.startswith("#") else "#" + candidate
        key = name.lstrip("#").lower()
        if key in seen or key in existing_norm:
            continue
        seen.add(key)
        selected.append(name)
        if len(selected) >= limit:
            break
    return selected


def enforce_max_hashtags(hashtags_value: Any, max_hashtags: int = DEFAULT_MAX_HASHTAGS) -> list[str]:
    """Enforce une limite maximale de hashtags et dedupe."""
    names = normalize_hashtag_list(hashtags_value)
    unique: list[str] = []
    seen: set[str] = set()
    for h in names:
        key = h.lstrip("#").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(h)
    result: list[str] = []
    for h in unique:
        if len(result) >= max_hashtags:
            break
        result.append(h)
    return result
