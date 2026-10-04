"""Recherche de photos en langage naturel.

Stratégie (jamais d'exclusive LLM) :
1. heuristique locale : stop-words + correspondance sur personnes, tags,
   lieux, appareils, titre et nom de fichier ;
2. si ``PHOTO_AI_SEARCH_ENABLED`` et que l'heuristique n'a rien conclu,
   l'AI Gateway traduit la requête en filtres structurés (JSON) — en cas
   d'indisponibilité, on retombe silencieusement sur l'heuristique.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import PhotoPerson, PhotoPlace, PhotoTag

logger = logging.getLogger(__name__)

STOPWORDS = {
    # français
    "de", "des", "du", "la", "le", "les", "un", "une", "au", "aux", "en", "dans",
    "par", "pour", "avec", "sur", "sous", "et", "ou", "où", "qui", "que", "quoi",
    "ce", "cet", "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes", "son",
    "sa", "ses", "leur", "leurs", "photo", "photos", "image", "images", "est",
    "sont", "il", "elle", "ils", "elles", "je", "tu", "nous", "vous", "y", "a",
    "d", "l", "n", "s", "c", "qu", "plus", "moins", "très", "tous", "tout",
    "toute", "toutes", "mes", "nos", "vos",
    # anglais
    "the", "of", "in", "on", "at", "and", "or", "with", "from", "to", "is",
    "are", "my", "our", "their", "this", "that", "these", "those", "by", "an",
    "be", "it", "its", "photos", "picture", "pictures",
}

_TOKEN_RE = re.compile(r"[a-z0-9à-öø-ÿ]+", re.IGNORECASE)


def tokenize(query: str) -> list[str]:
    tokens = []
    for token in _TOKEN_RE.findall(query or ""):
        lowered = token.lower()
        if len(lowered) < 2 or lowered in STOPWORDS:
            continue
        tokens.append(lowered)
    return tokens


def _norm(value: str) -> str:
    return (value or "").strip().lower()


async def heuristic_parse(
    db: AsyncSession, owner_id: int, query: str
) -> dict[str, Any]:
    """Parse local : personnes, tags, lieux + texte libre restant."""
    filters: dict[str, Any] = {}
    lowered = _norm(query)
    tokens = tokenize(query)
    if not lowered:
        return filters

    remaining = list(tokens)

    # Personnes : « photos avec Manu » / « photos de Manu »
    people = (
        await db.execute(
            select(PhotoPerson).where(PhotoPerson.owner_id == owner_id)
        )
    ).scalars().all()
    matched_people = []
    for person in people:
        name = _norm(person.name)
        if name and name in lowered:
            matched_people.append(person.id)
            for token in name.split():
                if token in remaining:
                    remaining.remove(token)
    if matched_people:
        filters["person_ids"] = matched_people

    # Tags : « montagne », « plage », « coucher de soleil »...
    tags = (
        await db.execute(select(PhotoTag).where(PhotoTag.owner_id == owner_id))
    ).scalars().all()
    matched_tags = []
    for tag in tags:
        name = _norm(tag.name)
        slug = _norm(tag.slug)
        if not name:
            continue
        if name in lowered or (slug and slug in lowered):
            matched_tags.append(tag.id)
            for token in (name + " " + slug).split():
                if token in remaining:
                    remaining.remove(token)
    if matched_tags:
        filters["tag_ids"] = matched_tags

    # Lieux : « en Espagne » / label de zone GPS
    places = (
        await db.execute(select(PhotoPlace).where(PhotoPlace.label != ""))
    ).scalars().all()
    matched_places = []
    for place in places:
        label = _norm(place.label)
        if label and label in lowered:
            matched_places.append(place.id)
            for token in label.split():
                if token in remaining:
                    remaining.remove(token)
        if place.country:
            country = _norm(place.country)
            if country and country in lowered:
                matched_places.append(place.id)
                for token in country.split():
                    if token in remaining:
                        remaining.remove(token)
    if matched_places:
        filters["place_ids"] = matched_places

    # Texte libre : les tokens qui n'ont résolu aucune entité complètent les
    # filtres (« photos de Manu au coucher de soleil » → personne + tag +
    # « coucher »/« soleil » restants). S'ils ne matchent rien, la recherche
    # reste honnête : aucun faux positif n'est ajouté.
    if remaining:
        filters["free_text"] = " ".join(remaining)
    return filters


async def ai_parse(db: AsyncSession, query: str) -> dict[str, Any] | None:
    """Traduit la requête en filtres structurés via l'AI Gateway (optionnel)."""
    from app.services.ai_gateway import ai_gateway

    system = (
        "Tu traduis une recherche de photos en filtres JSON stricts. "
        "Réponds UNIQUEMENT par un objet JSON de la forme : "
        '{"free_text": string, "people": [string], "tags": [string], '
        '"place": string|null, "date_from": "YYYY-MM-DD"|null, '
        '"date_to": "YYYY-MM-DD"|null, "favorite": boolean|null}. '
        "Les valeurs sont en minuscules. Aucune explication."
    )
    try:
        response = await ai_gateway.generate(
            prompt=f"Requête : {query}",
            system_prompt=system,
            task_type="fast",
        )
        text = (response.text or "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            return None
        return data
    except Exception as exc:  # noqa: BLE001 - la recherche doit toujours fonctionner
        logger.info("[PHOTO-SEARCH] parse IA indisponible: %s", exc)
        return None


async def build_search_filters(
    db: AsyncSession, owner_id: int, query: str
) -> dict[str, Any]:
    """Construit les filtres d'une requête naturelle (heuristique + IA optionnelle)."""
    settings = get_settings()
    filters = await heuristic_parse(db, owner_id, query)

    interesting = bool(filters.get("person_ids") or filters.get("tag_ids") or filters.get("place_ids"))
    if settings.PHOTO_AI_SEARCH_ENABLED and not interesting and (query or "").strip():
        ai_filters = await ai_parse(db, query)
        if ai_filters:
            filters = _merge_ai_filters(filters, ai_filters)

    return filters


def _merge_ai_filters(base: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any]:
    # Les chaînes renvoyées par le modèle sont reconverties en IDs quand
    # elles correspondent à des entités connues ; sinon texte libre.
    merged = dict(base)
    parts: list[str] = []
    if ai.get("free_text"):
        parts.append(str(ai["free_text"]))
    tags = ai.get("tags")
    if isinstance(tags, list):
        parts.extend(str(tag) for tag in tags if tag)
    free_text = " ".join(parts).strip()
    has_entities = bool(
        merged.get("person_ids")
        or merged.get("tag_ids")
        or merged.get("place_ids")
        or merged.get("people_names")
        or merged.get("place_name")
    )
    if free_text and not has_entities:
        merged["free_text"] = (merged.get("free_text", "") + " " + free_text).strip()
    if isinstance(ai.get("people"), list) and ai["people"]:
        merged.setdefault("people_names", [str(p) for p in ai["people"] if p])
    if isinstance(ai.get("place"), str) and ai["place"].strip():
        merged.setdefault("place_name", ai["place"].strip())
    if ai.get("date_from"):
        merged.setdefault("date_from", str(ai["date_from"]))
    if ai.get("date_to"):
        merged.setdefault("date_to", str(ai["date_to"]))
    if ai.get("favorite") is True:
        merged.setdefault("favorite", True)
    return merged
