"""Service Studio Community Manager V2 - Création intelligente de publications."""

import json
import logging
import os
import random
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.photo import Photo
from app.models.sport import (
    CommunityManagerStrategy,
    EditorialCalendarEntry,
    SportActivity,
    SportAthlete,
    SportPublication,
)
from app.models.user import User
from app.schemas.sport import (
    PublicationDraftUpdate,
    PublicationGenerateFromCalendarRequest,
    PublicationGenerateTextRequest,
    PublicationValidateRequest,
    PublicationPreviewRequest,
)
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.sport_publications import (
    SportPublicationService,
    SYSTEM_PROMPT,
    STYLE_LABELS,
    STYLE_INSTRUCTIONS,
    clean_caption_text,
    clean_hashtags,
)
from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
from app.services.sport_media_publish import MediaPublishService

logger = logging.getLogger(__name__)

INSTAGRAM_CAPTION_MAX_LENGTH = 2200

def build_full_caption(title: Optional[str], content: Optional[str], hashtags: Optional[str]) -> str:
    """Construit la légende Instagram complète : titre + accroche + hashtags.
    
    Format :
    [TITRE]
    
    [ACCROCHE]
    
    [HASHTAGS]
    
    Règles :
    - Supprime les champs vides
    - Pas de doublons d'espaces/retours à la ligne
    - Préserve les emojis et accents
    """
    parts = []
    if title and title.strip():
        parts.append(title.strip())
    if content and content.strip():
        parts.append(content.strip())
    if hashtags and hashtags.strip():
        parts.append(hashtags.strip())
    return "\n\n".join(parts)


def _extract_stats_html(content: str) -> str:
    """Extrait les stats du contenu et génère un HTML léger pour le mode stratégique."""
    if not content:
        return ""
    
    # Patterns pour extraire les stats courantes (distance, dénivelé, durée, FC, allure, etc.)
    stats = []
    
    # Distance (km)
    dist_match = re.search(r'(\d+(?:[.,]\d+)?)\s*km', content, re.IGNORECASE)
    if dist_match:
        stats.append(f"🏃 {dist_match.group(1)} km")
    
    # Dénivelé (D+)
    elev_match = re.search(r'(\d+)\s*[mM]\s*[Dd][\+]?', content)
    if elev_match:
        stats.append(f"⛰️ {elev_match.group(1)} m D+")
    
    # Durée
    dur_match = re.search(r'(\d+h\d{2}min|\d+h\d{2}|\d+min)', content)
    if dur_match:
        stats.append(f"⏱️ {dur_match.group(1)}")
    
    # FC moyenne
    fc_match = re.search(r'FC\s*(?:moy|moyenne)?\s*[=:]\s*(\d+)', content, re.IGNORECASE)
    if fc_match:
        stats.append(f"❤️ {fc_match.group(1)} bpm")
    
    # Allure
    pace_match = re.search(r'(?:allure|pace)\s*[=:]\s*(\d+[\':]\d{2})', content, re.IGNORECASE)
    if pace_match:
        stats.append(f"⚡ {pace_match.group(1)}/km")
    
    if not stats:
        return ""
    
    stats_html = "".join(f'<span style="background: #f0f0f0; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500;">{s}</span>' for s in stats)
    return f'<div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">{stats_html}</div>'


# --- Publications sportives : overlay stats + audio ---

SPORT_MUSIC_TRACKS = [
    "calm-piano.mp3",
    "city-sunshine.mp3",
    "happy-ukulele.mp3",
    "infinite-peace.mp3",
    "lovely-piano.mp3",
    "mysterious-lights.mp3",
    "nomadic-sunset.mp3",
    "nostalgia-piano.mp3",
    "space-ambience.mp3",
]

# Catégories simples pour un choix "intelligent" (heuristique) + aléatoire
_SPORT_MUSIC_ENERGETIC = ["city-sunshine.mp3", "happy-ukulele.mp3", "mysterious-lights.mp3"]
_SPORT_MUSIC_CALM = ["calm-piano.mp3", "infinite-peace.mp3", "lovely-piano.mp3", "nostalgia-piano.mp3", "space-ambience.mp3", "nomadic-sunset.mp3"]


def _is_sport_publication(pub: SportPublication) -> bool:
    entry = getattr(pub, "calendar_entry", None)
    if getattr(pub, "source", None) == "garmin":
        return True
    if getattr(pub, "content_type", None) == "publication_sportive":
        return True
    if getattr(pub, "activity_id", None):
        # activité liée => publication sportive Garmin
        return True
    if entry is not None:
        if getattr(entry, "source", None) == "garmin":
            return True
        if getattr(entry, "content_type", None) == "publication_sportive":
            return True
        if getattr(entry, "source_activity_id", None):
            return True
    return False


def _format_duration(seconds: int | None) -> str | None:
    if not seconds:
        return None
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h}h{m:02d}"
    return f"{m} min"


def _sport_stats_from_activity(activity: SportActivity | None) -> dict[str, str]:
    if activity is None:
        return {}
    stats: dict[str, str] = {}
    if getattr(activity, "distance_m", None) is not None:
        stats["distance"] = f"{activity.distance_m / 1000:.1f} km"
    if getattr(activity, "elevation_gain_m", None) is not None:
        stats["denivele"] = f"{int(activity.elevation_gain_m)} m D+"
    dur = _format_duration(getattr(activity, "duration_seconds", None))
    if dur:
        stats["duree"] = dur
    return stats


def _merge_design(base: dict | None, patch: dict | None) -> dict:
    """Fusionne un patch design dans un design existant sans écraser les clés non fournies."""
    base = dict(base or {})
    patch = dict(patch or {})
    merged = dict(base)
    list_keys = ("elements", "timeline", "subtitles", "carousel")
    for key, value in patch.items():
        if key in list_keys and isinstance(value, list):
            merged[key] = value
        elif key in ("background", "format") and isinstance(value, dict):
            merged[key] = {**(base.get(key) or {}), **value}
        else:
            merged[key] = value
    return merged


def _sport_stats_elements_to_add(design: dict, activity: SportActivity | None) -> list[dict]:
    """Construit les elements graphiques `sport_stats` (distance / denivele / duree) pour une activite."""
    elements = design.get("elements") if isinstance(design, dict) else None
    if isinstance(elements, list) and any(
        isinstance(e, dict) and e.get("type") == "sport_stats" for e in elements
    ):
        return []
    if activity is None:
        return []
    fmt = design.get("format") if isinstance(design, dict) else None
    w = float((fmt or {}).get("width") or 1080)
    h = float((fmt or {}).get("height") or 1350)
    dist_m = getattr(activity, "distance_m", None)
    elev = getattr(activity, "elevation_gain_m", None)
    dur = getattr(activity, "duration_seconds", None)
    specs: list[tuple[str, str, str, str]] = []
    if dist_m is not None:
        specs.append(("distance", "DISTANCE", f"{dist_m / 1000:.1f}", "km"))
    if elev is not None:
        specs.append(("denivele", "DÉNIVELÉ", str(int(elev)), "m D+"))
    if dur:
        specs.append(("duree", "TEMPS", _format_duration(int(dur)) or "", ""))
    new_els: list[dict] = []
    for stat, label, value, unit in specs:
        new_els.append(
            {
                "id": f"el-stats-{stat}",
                "type": "sport_stats",
                "stat": stat,
                "label": label,
                "value": value,
                "unit": unit,
                "x": w / 2,
                "y": h / 2,
                "w": w * 0.6,
                "h": max(40, int(h * 0.16)),
                "size": max(24, int(w * 0.07)),
                "font": "Arial",
                "color": "#ffffff",
                "bold": True,
                "italic": False,
                "shadow": True,
                "align": "center",
                "rotation": 0,
                "opacity": 1,
            }
        )
    return new_els


def pick_sport_music(activity: SportActivity | None) -> str:
    """Choix 'intelligent' (heuristique) + aléatoire d'une piste audio."""
    pool = SPORT_MUSIC_TRACKS
    if activity is not None:
        dist_km = (activity.distance_m or 0) / 1000 if getattr(activity, "distance_m", None) else 0
        elev = getattr(activity, "elevation_gain_m", None) or 0
        dur = getattr(activity, "duration_seconds", None) or 0
        # Sorties longues/intenses -> pistes plus énergiques, sinon calmes
        if dist_km >= 15 or elev >= 500 or dur >= 5400:
            pool = _SPORT_MUSIC_ENERGETIC
        else:
            pool = _SPORT_MUSIC_CALM
    return random.choice(pool)


def render_sport_overlay_image(photo_path: str, stats: dict[str, str], out_path: str) -> str | None:
    """Dessine durée, dénivelé et kilomètres sur la photo. Retourne out_path ou None."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except Exception:
        return None
    if not stats:
        return None
    try:
        with Image.open(photo_path) as src:
            img = ImageOps.exif_transpose(src).convert("RGBA")
        w, h = img.size
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Bandeau bas semi-transparent
        band_h = max(int(h * 0.16), 140)
        y0 = h - band_h
        draw.rectangle([(0, y0), (w, h)], fill=(0, 0, 0, 150))

        # Police
        def load_font(size):
            for path in (
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            ):
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    continue
            return ImageFont.load_default()

        font_label = load_font(max(int(h * 0.022), 18))
        font_value = load_font(max(int(h * 0.045), 30))

        items = []
        if "duree" in stats:
            items.append(("DURÉE", stats["duree"]))
        if "denivele" in stats:
            items.append(("DÉNIVELÉ", stats["denivele"]))
        if "distance" in stats:
            items.append(("DISTANCE", stats["distance"]))
        if not items:
            return None

        n = len(items)
        col_w = w / n
        for i, (label, value) in enumerate(items):
            cx = int(col_w * i + col_w / 2)
            # label
            try:
                lb = draw.textbbox((0, 0), label, font=font_label)
                lw = lb[2] - lb[0]
            except Exception:
                lw = len(label) * 8
            try:
                vb = draw.textbbox((0, 0), value, font=font_value)
                vw = vb[2] - vb[0]
                vh = vb[3] - vb[1]
            except Exception:
                vw = len(value) * 14
                vh = 30
            ly = y0 + int(band_h * 0.18)
            vy = y0 + int(band_h * 0.45)
            draw.text((cx - lw / 2, ly), label, fill=(220, 220, 220, 255), font=font_label)
            draw.text((cx - vw / 2, vy), value, fill=(255, 255, 255, 255), font=font_value)

        out = Image.alpha_composite(img, overlay).convert("RGB")
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        out.save(out_path, format="JPEG", quality=92, optimize=True)
        return out_path
    except Exception:
        logger.exception("[CM-STUDIO] Overlay stats sport impossible")
        return None


class CommunityManagerStudioService:
    """Service pour le Studio de création V2."""

    # Instagram autorise au maximum 2 200 caractères dans une légende.
    INSTAGRAM_CAPTION_MAX_LENGTH: int = 2200

    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.pub_service = SportPublicationService(db, current_user)

    async def _get_athlete_and_strategy(self) -> tuple[SportAthlete, CommunityManagerStrategy]:
        """Récupère l'athlète et sa stratégie."""
        athlete = await self.pub_service.get_or_create_athlete()
        strategy_result = await self.db.execute(
            select(CommunityManagerStrategy).where(
                CommunityManagerStrategy.athlete_id == athlete.id
            )
        )
        strategy = strategy_result.scalar_one_or_none()
        if not strategy:
            raise ValueError("Stratégie éditoriale non configurée")
        return athlete, strategy

    async def create_draft_from_calendar(
        self, data: PublicationGenerateFromCalendarRequest
    ) -> SportPublication:
        """Crée un brouillon de publication depuis une entrée de calendrier validée."""
        # Vérifier l'entrée de calendrier
        athlete, strategy = await self._get_athlete_and_strategy()

        entry_result = await self.db.execute(
            select(EditorialCalendarEntry).where(
                EditorialCalendarEntry.id == data.calendar_entry_id,
                EditorialCalendarEntry.strategy_id == strategy.id,
            )
        )
        entry = entry_result.scalar_one_or_none()
        if not entry:
            raise ValueError("Entrée de calendrier introuvable")

        if entry.status not in ("planifié", "accepted"):
            raise ValueError("L'entrée doit être validée (statut 'planifié' ou 'accepted') pour créer une publication")

        # Utiliser le service existant pour générer
        gen_request = type("GenRequest", (), {
            "styles": data.styles,
            "custom_instructions": data.custom_instructions,
            "tone": data.tone,
            "visual_type": data.visual_type,
            "photo_id": data.photo_id,
        })()

        publication = await self.pub_service.generate_from_calendar_entry(
            data.calendar_entry_id, gen_request
        )
        return publication

    async def get_draft(self, publication_id: int) -> Optional[SportPublication]:
        """Récupère un brouillon de publication (avec entrée de calendrier si V2)."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None
        # Charger la relation calendar_entry si V2
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                ).options(selectinload(EditorialCalendarEntry.strategy))
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        # Charger l'activité liée pour les publications sportives (données Garmin pour sport_stats)
        if pub.activity_id:
            await self.db.refresh(pub, attribute_names=['activity'])
        # Une réponse IA non parsée peut être stockée en JSON brut : afficher le
        # texte lisible (ce qui sera réellement publié). Non commité : la
        # correction durable passe par l'enregistrement du formulaire.
        # Pour les publications sportives V2 (depuis calendrier) : garantir les elements
        # graphiques sport_stats (Garmin -> design). Pour V1 (depuis activité directe),
        # n'ajouter les stats que si un design existe déjà.
        if _is_sport_publication(pub):
            is_v2 = getattr(pub, "created_from", None) == "calendar"
            has_design = isinstance(pub.design, dict) and pub.design
            if is_v2 or has_design:
                design0 = pub.design if isinstance(pub.design, dict) else {}
                design = dict(design0)
                activity = await self._get_activity_for_publication(pub)
                new_stats = _sport_stats_elements_to_add(design, activity)
                if new_stats:
                    design["elements"] = list(design.get("elements") or []) + new_stats
                    pub.design = design
        cleaned_content = clean_caption_text(pub.content)
        if cleaned_content and cleaned_content != pub.content:
            pub.content = cleaned_content
        cleaned_hashtags = clean_hashtags(pub.hashtags)
        if cleaned_hashtags and cleaned_hashtags != pub.hashtags:
            pub.hashtags = cleaned_hashtags
        return pub

    async def update_draft(
        self, publication_id: int, data: PublicationDraftUpdate
    ) -> Optional[SportPublication]:
        """Met à jour un brouillon (texte, hashtags, visuel, ton, propositions)."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None

        # Vérifier que l'utilisateur a le droit (déjà fait par get_publication)

        # Mettre à jour les champs fournis (texte/hashtags/titre toujours modifiables
        # pour stories et publications sportives, sauf publication partagée gérée côté statut/UI)
        if data.title is not None:
            pub.title = data.title
        if data.content is not None:
            pub.content = data.content
        if data.hashtags is not None:
            pub.hashtags = data.hashtags
        if "photo_id" in data.model_fields_set:
            if not pub.photo_locked:
                pub.photo_id = data.photo_id
        if data.visual_type is not None:
            if not pub.photo_locked:
                pub.visual_type = data.visual_type
        if data.tone_used is not None:
            pub.tone_used = data.tone_used
        if data.visual_generation_prompt is not None:
            pub.visual_generation_prompt = data.visual_generation_prompt
        if data.visual_generation_provider is not None:
            pub.visual_generation_provider = data.visual_generation_provider
        if data.selected_proposal is not None:
            pub.selected_proposal = data.selected_proposal
            if data.content is None and data.title is None and data.hashtags is None:
                idx = data.selected_proposal
                if isinstance(pub.proposals, list) and 0 <= idx < len(pub.proposals):
                    p = pub.proposals[idx]
                    if isinstance(p, dict):
                        pub.title = p.get("title") or pub.title
                        pub.content = p.get("content")
                        pub.hashtags = p.get("hashtags")
        if data.proposals is not None:
            pub.proposals = data.proposals
        if data.styles is not None:
            # Valider les styles (même logique que sport_publications._validate_styles)
            from app.services.sport_publications import VALID_STYLES

            cleaned = []
            for s in data.styles or []:
                s = (s or "").strip().lower()
                if s in VALID_STYLES and s not in cleaned:
                    cleaned.append(s)
            pub.styles = cleaned or pub.styles
        if data.custom_instructions is not None:
            pub.custom_instructions = data.custom_instructions.strip() or None
        if data.design is not None:
            pub.design = _merge_design(pub.design, data.design)
        # Lock fields
        if data.title_locked is not None:
            pub.title_locked = data.title_locked
        if data.content_locked is not None:
            pub.content_locked = data.content_locked
        if data.photo_locked is not None:
            pub.photo_locked = data.photo_locked

        # Si le contenu ou le titre est modifié après validation, invalider la validation
        if pub.status == "validated" and (data.content is not None or data.title is not None):
            pub.status = "draft"
            pub.validated_at = None

        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def generate_text_variants(
        self,
        publication_id: int,
        tone: Optional[str] = None,
        styles: Optional[list[str]] = None,
        custom_instructions: Optional[str] = None,
        count: int = 3,
    ) -> list[dict[str, Any]]:
        """Génère des variantes de texte pour un brouillon existant."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")

        if not pub.calendar_entry_id:
            raise ValueError("Variantes uniquement disponibles pour publications V2 (depuis calendrier)")

        athlete, strategy = await self._get_athlete_and_strategy()

        entry_result = await self.db.execute(
            select(EditorialCalendarEntry).where(
                EditorialCalendarEntry.id == pub.calendar_entry_id,
                EditorialCalendarEntry.strategy_id == strategy.id,
            )
        )
        entry = entry_result.scalar_one_or_none()
        if not entry:
            raise ValueError("Entrée de calendrier introuvable")

        # Récupérer activités récentes
        activities_result = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id)
            .order_by(SportActivity.started_at.desc())
            .limit(10)
        )
        recent_activities = []
        for act in activities_result.scalars().all():
            recent_activities.append({
                "id": act.id,
                "sport_type": act.sport_type,
                "activity_name": act.activity_name,
                "started_at": act.started_at.isoformat() if act.started_at else None,
                "duration_seconds": act.duration_seconds,
                "distance_m": act.distance_m,
                "elevation_gain_m": act.elevation_gain_m,
                "elevation_loss_m": act.elevation_loss_m,
                "avg_speed_m_s": act.avg_speed_m_s,
                "avg_pace_sec_km": act.avg_pace_sec_km,
                "avg_heart_rate": act.avg_heart_rate,
                "max_heart_rate": act.max_heart_rate,
                "avg_cadence": act.avg_cadence,
                "avg_power_w": act.avg_power_w,
                "calories": act.calories,
                "temperature_c": act.temperature_c,
                "source_type": act.source_type,
            })

        # Historique pour éviter répétition
        prev_rows = (
            await self.db.execute(
                select(SportPublication).where(
                    SportPublication.athlete_id == pub.athlete_id,
                    SportPublication.id != pub.id,
                ).order_by(SportPublication.created_at.desc()).limit(8)
            )
        ).scalars().all()
        from app.services.sport_publications import _previous_publications_context
        prev_ctx = _previous_publications_context(list(prev_rows))

        effective_styles = styles or pub.styles or ["stats"]
        effective_tone = tone or pub.tone_used
        effective_custom = custom_instructions or pub.custom_instructions

        style_lines = "\n".join(
            f"- {STYLE_LABELS.get(s, s)} : {STYLE_INSTRUCTIONS.get(s, '')}" for s in effective_styles
        )
        if effective_custom:
            style_lines += f"\n- Consignes personnalisées : {effective_custom}"
        if effective_tone:
            style_lines += f"\n- Ton rédactionnel : {effective_tone}"

        mix_note = ""
        if len(effective_styles) > 1:
            mix_note = " Mode MIX : combiner les tons sélectionnés."

        prompt = (
            f"Sujet éditorial (déjà validé) :\n"
            f"- Titre : {entry.topic}\n"
            f"- Thème : {entry.theme or 'Non défini'}\n"
            f"- Objectif : {entry.objective or 'Non défini'}\n"
            f"- Note IA : {entry.notes or 'Aucune'}\n"
            f"- Date suggérée : {entry.date}\n\n"
            f"Stratégie éditoriale :\n"
            f"- Identité : {strategy.brand_identity or 'Non définie'}\n"
            f"- Tons : {', '.join(strategy.tone) if strategy.tone else 'Non définis'}\n"
            f"- Audience : {strategy.target_audience or 'Non définie'}\n"
            f"- Objectifs : {', '.join(strategy.objectives) if strategy.objectives else 'Non définis'}\n"
            f"- Thèmes : {', '.join(strategy.themes) if strategy.themes else 'Non définis'}\n\n"
            f"Activités récentes Garmin (données réelles) :\n"
            f"{json.dumps(recent_activities[:5], ensure_ascii=False, default=str)}\n\n"
            f"Tons demandés :\n{style_lines}{mix_note}\n\n"
            f"Historique des publications précédentes (à éviter) :\n{prev_ctx}\n\n"
            f"Génère {count} variantes de texte distinctes pour ce même sujet. "
            f"Pour chaque variante retourne : title, content, hashtags, format, idee_visuelle, objectif. "
            f"Respecte le ton et n'invente AUCUNE donnée. "
            f"IMPORTANT : le texte (content + hashtags combinés) ne doit PAS dépasser {self.INSTAGRAM_CAPTION_MAX_LENGTH} caractères au total. "
            f"Réponds uniquement en JSON avec la clé 'proposals'."
        )

        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=1800,
            )
        except AIGatewayError as exc:
            logger.warning("[CM-STUDIO] IA indisponible pour variantes : %s", exc)
            raise

        text = (response.text or "").strip()
        payload = None
        try:
            cleaned = text
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            s, e = cleaned.find("{"), cleaned.rfind("}")
            if s >= 0 and e > s:
                payload = json.loads(cleaned[s:e + 1])
        except (json.JSONDecodeError, ValueError):
            payload = None

        proposals = []
        if isinstance(payload, dict) and isinstance(payload.get("proposals"), list):
            for p in payload["proposals"][:count]:
                if not isinstance(p, dict):
                    continue
                content = clean_caption_text(p.get("content"))
                if not content:
                    continue
                hashtags = clean_hashtags(p.get("hashtags"))
                # Tronçage automatique si la légende complète dépasse la limite Instagram
                full_caption = content + (f"\n\n{hashtags}" if hashtags else "")
                if len(full_caption) > self.INSTAGRAM_CAPTION_MAX_LENGTH:
                    # Priorité : conserver les hashtags, tronquer le contenu en premier
                    if hashtags:
                        hashtag_part_len = len("\n\n" + hashtags)
                        content_max = self.INSTAGRAM_CAPTION_MAX_LENGTH - hashtag_part_len - 3  # place pour "..."
                        if content_max > 50:
                            content = content[:content_max].rstrip() + "..."
                            full_caption = content + "\n\n" + hashtags
                        # Si même avec le contenu très court ça dépasse encore, tronquer les hashtags
                        if len(full_caption) > self.INSTAGRAM_CAPTION_MAX_LENGTH:
                            hashtag_max = self.INSTAGRAM_CAPTION_MAX_LENGTH - len(content) - 3
                            if hashtag_max > 10:
                                hashtags = hashtags[:hashtag_max].rstrip() + "..."
                    else:
                        content = content[:self.INSTAGRAM_CAPTION_MAX_LENGTH - 3].rstrip() + "..."
                proposals.append({
                    "title": str(p.get("title")).strip() if p.get("title") else None,
                    "content": content,
                    "hashtags": hashtags,
                    "format": str(p.get("format")).strip() if p.get("format") else "photo",
                    "idee_visuelle": str(p.get("idee_visuelle")).strip() if p.get("idee_visuelle") else None,
                    "objectif": str(p.get("objectif")).strip() if p.get("objectif") else None,
                })

        if not proposals:
            proposals = [{"title": "Variante", "content": clean_caption_text(text), "hashtags": None, "format": "photo", "idee_visuelle": None, "objectif": None}]

        return proposals[:count]

    async def generate_text(
        self,
        publication_id: int,
        data: PublicationGenerateTextRequest,
    ) -> Optional[SportPublication]:
        """Génère un texte court ou long selon le ton."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")

        if pub.content_locked:
            raise ValueError("Le texte est verrouillé. Déverrouillez-le pour générer un nouveau texte.")

        if not pub.calendar_entry_id:
            raise ValueError("Génération de texte uniquement disponible pour publications V2 (depuis calendrier)")

        athlete, strategy = await self._get_athlete_and_strategy()

        entry_result = await self.db.execute(
            select(EditorialCalendarEntry).where(
                EditorialCalendarEntry.id == pub.calendar_entry_id,
                EditorialCalendarEntry.strategy_id == strategy.id,
            )
        )
        entry = entry_result.scalar_one_or_none()
        if not entry:
            raise ValueError("Entrée de calendrier introuvable")

        # Récupérer activités récentes
        activities_result = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id)
            .order_by(SportActivity.started_at.desc())
            .limit(10)
        )
        recent_activities = []
        for act in activities_result.scalars().all():
            recent_activities.append({
                "id": act.id,
                "sport_type": act.sport_type,
                "activity_name": act.activity_name,
                "started_at": act.started_at.isoformat() if act.started_at else None,
                "duration_seconds": act.duration_seconds,
                "distance_m": act.distance_m,
                "elevation_gain_m": act.elevation_gain_m,
                "elevation_loss_m": act.elevation_loss_m,
                "avg_speed_m_s": act.avg_speed_m_s,
                "avg_pace_sec_km": act.avg_pace_sec_km,
                "avg_heart_rate": act.avg_heart_rate,
                "max_heart_rate": act.max_heart_rate,
                "avg_cadence": act.avg_cadence,
                "avg_power_w": act.avg_power_w,
                "calories": act.calories,
                "temperature_c": act.temperature_c,
                "source_type": act.source_type,
            })

        # Historique pour éviter répétition
        prev_rows = (
            await self.db.execute(
                select(SportPublication).where(
                    SportPublication.athlete_id == pub.athlete_id,
                    SportPublication.id != pub.id,
                ).order_by(SportPublication.created_at.desc()).limit(8)
            )
        ).scalars().all()
        from app.services.sport_publications import _previous_publications_context
        prev_ctx = _previous_publications_context(list(prev_rows))

        effective_tone = data.tone or pub.tone_used
        effective_styles = data.styles or pub.styles or ["stats"]
        effective_custom = data.custom_instructions or pub.custom_instructions

        style_lines = "\n".join(
            f"- {STYLE_LABELS.get(s, s)} : {STYLE_INSTRUCTIONS.get(s, '')}" for s in effective_styles
        )
        if effective_custom:
            style_lines += f"\n- Consignes personnalisées : {effective_custom}"
        if effective_tone:
            style_lines += f"\n- Ton rédactionnel : {effective_tone}"

        length_instruction = ""
        if data.length == "short":
            length_instruction = "Génère un texte COURT (max 3-4 lignes, accrocheur, percutant)."
        else:
            length_instruction = "Génère un texte LONG (plus développé, narratif, avec contexte et détails)."

        title_instruction = ""
        if pub.title:
            title_instruction = f"\nLe titre actuel est : \"{pub.title}\". Tu peux le conserver ou en proposer un plus accrocheur, en cohérence avec le ton choisi."
        else:
            title_instruction = "\nPropose un titre accrocheur et percutant en cohérence avec le ton choisi."

        mix_note = ""
        if len(effective_styles) > 1:
            mix_note = " Mode MIX : combiner les tons sélectionnés dans une même proposition quand c'est pertinent."

        prompt = (
            f"Sujet éditorial (déjà validé) :\n"
            f"- Titre : {entry.topic}\n"
            f"- Thème : {entry.theme or 'Non défini'}\n"
            f"- Objectif : {entry.objective or 'Non défini'}\n"
            f"- Note IA : {entry.notes or 'Aucune'}\n"
            f"- Date suggérée : {entry.date}\n\n"
            f"Stratégie éditoriale :\n"
            f"- Identité : {strategy.brand_identity or 'Non définie'}\n"
            f"- Tons : {', '.join(strategy.tone) if strategy.tone else 'Non définis'}\n"
            f"- Audience : {strategy.target_audience or 'Non définie'}\n"
            f"- Objectifs : {', '.join(strategy.objectives) if strategy.objectives else 'Non définis'}\n"
            f"- Thèmes : {', '.join(strategy.themes) if strategy.themes else 'Non définis'}\n\n"
            f"Activités récentes Garmin (données réelles) :\n"
            f"{json.dumps(recent_activities[:5], ensure_ascii=False, default=str)}\n\n"
            f"Tons demandés :\n{style_lines}{mix_note}\n\n"
            f"Historique des publications précédentes (à éviter) :\n{prev_ctx}\n\n"
            f"{length_instruction}{title_instruction}\n\n"
            f"Génère UNE SEULE proposition de texte. "
            f"Pour chaque proposition retourne : title, content, hashtags. "
            f"Respecte le ton et n'invente AUCUNE donnée. "
            f"IMPORTANT : le texte (content + hashtags combinés) ne doit PAS dépasser {self.INSTAGRAM_CAPTION_MAX_LENGTH} caractères au total. "
            f"Réponds uniquement en JSON avec la clé 'proposal'."
        )

        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=1200,
            )
        except AIGatewayError as exc:
            logger.warning("[CM-STUDIO] IA indisponible pour génération texte : %s", exc)
            raise

        text = (response.text or "").strip()
        payload = None
        try:
            cleaned = text
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```", 2)[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
            s, e = cleaned.find("{"), cleaned.rfind("}")
            if s >= 0 and e > s:
                payload = json.loads(cleaned[s:e + 1])
        except (json.JSONDecodeError, ValueError):
            payload = None

        proposal = None
        if isinstance(payload, dict) and isinstance(payload.get("proposal"), dict):
            proposal = payload["proposal"]
        elif isinstance(payload, dict) and isinstance(payload.get("proposals"), list) and payload["proposals"]:
            proposal = payload["proposals"][0]

        if not proposal:
            proposal = {"title": "Proposition", "content": text, "hashtags": None}

        # Tronçage automatique si la légende complète dépasse la limite Instagram
        proposal_content = clean_caption_text(proposal.get("content"))
        proposal_hashtags = clean_hashtags(proposal.get("hashtags"))
        full_caption = proposal_content + (f"\n\n{proposal_hashtags}" if proposal_hashtags else "")
        if len(full_caption) > self.INSTAGRAM_CAPTION_MAX_LENGTH:
            if proposal_hashtags:
                hashtag_part_len = len("\n\n" + proposal_hashtags)
                content_max = self.INSTAGRAM_CAPTION_MAX_LENGTH - hashtag_part_len - 3
                if content_max > 50:
                    proposal_content = proposal_content[:content_max].rstrip() + "..."
                    full_caption = proposal_content + "\n\n" + proposal_hashtags
                if len(full_caption) > self.INSTAGRAM_CAPTION_MAX_LENGTH:
                    hashtag_max = self.INSTAGRAM_CAPTION_MAX_LENGTH - len(proposal_content) - 3
                    if hashtag_max > 10:
                        proposal_hashtags = proposal_hashtags[:hashtag_max].rstrip() + "..."
            else:
                proposal_content = proposal_content[:self.INSTAGRAM_CAPTION_MAX_LENGTH - 3].rstrip() + "..."

        # Mettre à jour la publication (le texte et le titre doivent toujours être modifiables)
        if proposal.get("title"):
            pub.title = proposal.get("title")
        pub.content = proposal_content
        pub.hashtags = proposal_hashtags

        pub.tone_used = data.tone or pub.tone_used
        pub.styles = data.styles or pub.styles or ["stats"]

        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def validate_for_publication(
        self, publication_id: int, data: PublicationValidateRequest
    ) -> Optional[SportPublication]:
        """Valide un brouillon pour publication (passe en 'validated')."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None

        if not (pub.content or "").strip():
            raise ValueError("Le texte de la publication est vide")

        # Pour V2, vérifier aussi qu'il y a un visuel ou au moins une idée visuelle
        if pub.created_from == "calendar" and not pub.photo_id and not pub.visual_generation_prompt:
            logger.warning("[CM-STUDIO] Publication V2 sans visuel ni prompt de génération")

        pub.status = "validated"
        pub.validated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def schedule_publication(
        self, publication_id: int, scheduled_at: datetime
    ) -> Optional[SportPublication]:
        """Planifie une publication validée."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None

        if pub.status != "validated":
            raise ValueError("Seules les publications validées peuvent être planifiées")

        pub.status = "scheduled"
        pub.scheduled_at = scheduled_at
        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def get_preview(
        self, publication_id: int, format: str = "feed"
    ) -> dict[str, Any]:
        """Génère une prévisualisation HTML pour Instagram."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")

        # Charger l'entrée de calendrier si V2
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()

        # Publications sportives : appliquer overlay stats (durée, dénivelé, km) et choisir audio
        if _is_sport_publication(pub):
            pub = await self._ensure_sport_defaults(pub)
            await self.db.commit()
            await self.db.refresh(pub)

        # Rendu HTML simple pour prévisualisation
        content = clean_caption_text(pub.content) or ""
        hashtags = clean_hashtags(pub.hashtags) or ""
        title = pub.title or ""
        photo_url = None
        if pub.photo_id:
            # URL de fichier photo pour l'aperçu côté navigateur (authentification standard).
            # Ne pas utiliser de meta_token ici: les tokens de publication Meta sont à usage unique.
            photo_url = f"/photos/{pub.photo_id}/file?size=large"

        # Helper pour extraire les stats de l'activité Garmin si disponible
        stats_html = ""

        # Infos vidéo musicale compagnon (si disponible)
        companion = {
            "status": getattr(pub, "companion_video_status", "none"),
            "job_id": getattr(pub, "companion_video_job_id", None),
            "error": getattr(pub, "companion_video_error", None),
            "generated_at": pub.companion_video_generated_at.isoformat() if getattr(pub, "companion_video_generated_at", None) else None,
            "ready": bool(getattr(pub, "companion_video_status", None) == "ready" and getattr(pub, "companion_video_path", None)),
        }
        audio = (pub.design or {}).get("audio") if isinstance(pub.design, dict) else None
        if isinstance(audio, dict):
            from app.services.community_manager.audio import normalize_audio_config
            audio = normalize_audio_config(audio)

        # HTML de prévisualisation (style Instagram)
        if format == "feed":
            html = f"""
            <div style="max-width: 480px; background: #fff; border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="padding: 12px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #efefef;">
                    <div style="width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%);"></div>
                    <div>
                        <div style="font-weight: 600; font-size: 14px;">{self.current_user.username or 'Utilisateur'}</div>
                        <div style="font-size: 12px; color: #8e8e8e;">{datetime.now().strftime('%d/%m/%Y')}</div>
                    </div>
                </div>
                {f'<img src="{photo_url}" style="width: 100%; height: 480px; object-fit: cover;">' if photo_url else '<div style="width: 100%; height: 480px; background: #fafafa; display: flex; align-items: center; justify-content: center; color: #999;">Aucune image</div>'}
                <div style="padding: 12px 16px;">
                    {f'<div style="font-weight: 600; margin-bottom: 8px;">{title}</div>' if title else ''}
                    <div style="font-size: 14px; line-height: 1.5; white-space: pre-wrap;">{content}</div>
                    {f'<div style="margin-top: 12px; font-size: 13px; color: #8e8e8e; line-height: 1.6;">{hashtags}</div>' if hashtags else ''}
                </div>
                <div style="padding: 8px 16px; border-top: 1px solid #efefef; display: flex; gap: 16px; color: #8e8e8e; font-size: 13px;">
                    <span>♥️ 0</span>
                    <span>💬 0</span>
                    <span>📤 0</span>
                </div>
            </div>
            """
        elif format == "story":
            html = f"""
            <div style="width: 1080px; height: 1920px; background: #000; position: relative; color: white; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                {f'<img src="{photo_url}" style="width: 100%; height: 100%; object-fit: cover;">' if photo_url else ''}
                <div style="position: absolute; bottom: 100px; left: 40px; right: 40px; text-shadow: 0 2px 8px rgba(0,0,0,0.7);">
                    {f'<div style="font-size: 32px; font-weight: 700; margin-bottom: 16px;">{title}</div>' if title else ''}
                    <div style="font-size: 24px; line-height: 1.4;">{content}</div>
                    {f'<div style="margin-top: 24px; font-size: 20px; opacity: 0.9;">{hashtags}</div>' if hashtags else ''}
                </div>
            </div>
            """
        elif format == "strategic":
            # Mode stratégique : léger, juste stats + accroche courte, pas de blabla
            # Extraire les stats si disponibles dans le contenu
            stats_html = self._extract_stats_html(content)
            html = f"""
            <div style="max-width: 480px; background: #fff; border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="padding: 12px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #efefef;">
                    <div style="width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%);"></div>
                    <div>
                        <div style="font-weight: 600; font-size: 14px;">{self.current_user.username or 'Utilisateur'}</div>
                        <div style="font-size: 12px; color: #8e8e8e;">{datetime.now().strftime('%d/%m/%Y')}</div>
                    </div>
                </div>
                {f'<img src="{photo_url}" style="width: 100%; height: 480px; object-fit: cover;">' if photo_url else '<div style="width: 100%; height: 480px; background: #fafafa; display: flex; align-items: center; justify-content: center; color: #999;">Aucune image</div>'}
                <div style="padding: 12px 16px;">
                    {stats_html}
                    <div style="font-size: 14px; line-height: 1.5; white-space: pre-wrap; margin-top: 8px;">{content}</div>
                    {f'<div style="margin-top: 12px; font-size: 13px; color: #8e8e8e; line-height: 1.6;">{hashtags}</div>' if hashtags else ''}
                </div>
                <div style="padding: 8px 16px; border-top: 1px solid #efefef; display: flex; gap: 16px; color: #8e8e8e; font-size: 13px;">
                    <span>♥️ 0</span>
                    <span>💬 0</span>
                    <span>📤 0</span>
                </div>
            </div>
            """
        else:
            # Fallback reel/other
            html = f"""
            <div style="max-width: 480px; background: #fff; border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                <div style="padding: 12px 16px;">{title}</div>
                {f'<img src="{photo_url}" style="width: 100%;">' if photo_url else ''}
                <div style="padding: 12px 16px; white-space: pre-wrap;">{content}</div>
                {f'<div style="padding: 12px 16px; color: #8e8e8e;">{hashtags}</div>' if hashtags else ''}
            </div>
            """

        return {
            "publication_id": publication_id,
            "preview_html": html,
            "format": format,
            "companion_video": companion,
            "audio": audio,
        }

    async def _get_publication_with_context(self, publication_id: int) -> Optional[SportPublication]:
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        return pub

    async def _get_activity_for_publication(self, pub: SportPublication) -> SportActivity | None:
        if pub.activity_id:
            return await self.db.get(SportActivity, pub.activity_id)
        entry = getattr(pub, "calendar_entry", None)
        if entry and getattr(entry, "source_activity_id", None):
            return await self.db.get(SportActivity, entry.source_activity_id)
        return None

    async def _ensure_sport_defaults(self, pub: SportPublication) -> SportPublication:
        """Pour les publications sportives : overlay stats sur la photo + choix audio (intelligent/aléatoire)."""
        if not _is_sport_publication(pub):
            return pub

        activity = await self._get_activity_for_publication(pub)
        stats = _sport_stats_from_activity(activity)

        # Injection des elements graphiques sport_stats (distance / denivele / duree) depuis l'activite Garmin
        design0 = pub.design if isinstance(pub.design, dict) else {}
        design = dict(design0)
        new_stats = _sport_stats_elements_to_add(design, activity)
        if new_stats:
            design["elements"] = list(design.get("elements") or []) + new_stats
            pub.design = design

        # Overlay stats sur la photo (durée, dénivelé, km) - appliqué systématiquement
        if pub.photo_id and stats:
            try:
                from app.services.photo.service import PhotoService
                photo_service = PhotoService(self.db, self.current_user)
                photo = await photo_service._get_owned(pub.photo_id, include_deleted=True)
                storage = photo_service.storage
                src_path = storage.backend_for_photo(photo).original_path(photo.storage_path)
                if src_path and Path(src_path).is_file():
                    # Éviter de ré-appliquer si déjà un overlay sport généré pour cette photo/stats
                    design = pub.design if isinstance(pub.design, dict) else {}
                    sport_meta = design.get("sport_overlay") or {}
                    signature = f"{pub.photo_id}:{stats.get('duree')}:{stats.get('denivele')}:{stats.get('distance')}"
                    if sport_meta.get("signature") != signature or not sport_meta.get("overlay_photo_id"):
                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                            tmp_path = tmp.name
                        out = render_sport_overlay_image(str(src_path), stats, tmp_path)
                        if out:
                            try:
                                data = Path(out).read_bytes()
                                from app.core.config import get_settings
                                settings = get_settings()
                                # réutiliser la logique d'import simple (PhotoService ne permet pas d'injecter des bytes facilement)
                                from app.services.photo.metadata import sniff_image_format_maybe
                                from app.services.photo.storage import get_photo_storage
                                from uuid import uuid4
                                image_format = await sniff_image_format_maybe(data) or "jpeg"
                                if image_format == "jpg":
                                    image_format = "jpeg"
                                mime_type = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(image_format, "image/jpeg")
                                photo_storage = get_photo_storage()
                                backend = photo_storage.backend()
                                rel = photo_storage.save_original(
                                    self.current_user.id, uuid4().hex, f".{image_format}", data, backend.name
                                )
                                overlay_photo = Photo(
                                    owner_id=self.current_user.id,
                                    title=f"Overlay sport #{pub.id}",
                                    original_filename=f"sport_overlay_{pub.id}.{image_format}",
                                    storage_path=rel,
                                    storage_backend=backend.name,
                                    mime_type=mime_type,
                                    byte_size=len(data),
                                    taken_at=datetime.now(),
                                    content_hash=photo_storage.hash_bytes(data),
                                    status="ready",
                                    analysis_status="pending",
                                )
                                self.db.add(overlay_photo)
                                await self.db.flush()
                                # remplacer la photo de publication par la version avec overlay
                                pub.photo_id = overlay_photo.id
                                design = dict(design)
                                design["sport_overlay"] = {
                                    "signature": signature,
                                    "overlay_photo_id": overlay_photo.id,
                                    "stats": stats,
                                    "applied_at": datetime.now(timezone.utc).isoformat(),
                                }
                                pub.design = design
                            finally:
                                try:
                                    os.unlink(out)
                                except Exception:
                                    pass
                        else:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
            except Exception:
                logger.exception("[CM-STUDIO] Impossible d'appliquer l'overlay sport pour publication %s", pub.id)

        # Audio choisi intelligemment (heuristique) et aléatoirement - stocké dans le design
        try:
            from app.services.community_manager.audio import ensure_audio_config

            design = pub.design if isinstance(pub.design, dict) else {}
            design = ensure_audio_config(
                design,
                activity=activity,
                tone=getattr(pub, "tone_used", None),
                force=False,  # persisté : pas de changement à chaque chargement
            )
            pub.design = design
        except Exception:
            logger.exception("[CM-STUDIO] Impossible de sélectionner l'audio sport pour publication %s", pub.id)

        # Vidéo musicale compagnon (async, idempotente) : déclenchée si photo + audio prêts
        try:
            await self.ensure_companion_video_job(pub, force=False)
        except Exception:
            logger.exception("[CM-STUDIO] Impossible de planifier la vidéo compagnon pour publication %s", pub.id)

        await self.db.flush()
        return pub

    async def ensure_companion_video_job(self, pub: SportPublication, force: bool = False) -> Any:
        """Planifie (idempotent, async) le rendu vidéo musical compagnon d'une publication sportive.

        Conditions : publication sportive, photo présente, audio activé avec piste.
        Ne bloque pas ; le traitement est effectué par le worker photo_jobs (studio_render).
        """
        from app.core.config import get_settings
        from app.models.photo import PhotoJob
        from app.services.photo.jobs import enqueue_job, run_pending_jobs_now
        from app.services.community_manager.audio import normalize_audio_config, resolve_track_path

        if not _is_sport_publication(pub):
            return None

        # Pas de vidéo sans photo (overlay/stats appliqués sur la photo)
        if not pub.photo_id:
            return None

        design = pub.design if isinstance(pub.design, dict) else {}
        audio_cfg = normalize_audio_config(design.get("audio") if isinstance(design.get("audio"), dict) else {})
        track_id = audio_cfg.get("track_id") or audio_cfg.get("track")
        if not audio_cfg.get("enabled", True) or not track_id:
            return None
        # Fichier audio indisponible -> pas de rendu (évite jobs voués à l'échec en boucle)
        if resolve_track_path(str(track_id)) is None:
            return None

        # Idempotence : rendu déjà prêt et fichier présent
        if not force and pub.companion_video_status == "ready" and pub.companion_video_path:
            try:
                if Path(pub.companion_video_path).is_file():
                    return None
            except Exception:
                pass

        # Idempotence : rendu/job déjà en cours
        if not force and pub.companion_video_status in ("pending", "running"):
            return None

        # Vérifier l'absence de job actif existant pour cette publication
        existing = (
            await self.db.execute(
                select(PhotoJob).where(
                    PhotoJob.type == "studio_render",
                    PhotoJob.status.in_(("pending", "running")),
                )
            )
        ).scalars().all()
        for j in existing:
            p = j.payload_json or {}
            if p.get("kind") == "sport_companion_video" and str(p.get("publication_id")) == str(pub.id):
                # Réconcilier l'état publication si besoin
                if pub.companion_video_status not in ("ready", "running"):
                    pub.companion_video_status = "pending"
                    pub.companion_video_job_id = str(j.id)
                return j

        payload = {
            "kind": "sport_companion_video",
            "publication_id": pub.id,
            "user_id": getattr(self.current_user, "id", None),
            "duration": 12.0,
            "force": bool(force),
        }
        job = await enqueue_job(self.db, type="studio_render", photo_id=None, payload=payload, commit=False)

        pub.companion_video_status = "pending"
        pub.companion_video_job_id = str(job.id)
        pub.companion_video_error = None
        if force:
            pub.companion_video_generated_at = None
        # Refléter l'état audio "en attente d'intégration"
        design = {**design, "audio": {**audio_cfg, "embedded": False, "audio_status": "selected"}}
        pub.design = design

        # Déclenchement immédiat best-effort en contexte HTTP (sinon boucle lifespan)
        if get_settings().PHOTO_BACKGROUND_JOBS:
            try:
                import asyncio

                loop = asyncio.get_running_loop()
                loop.create_task(run_pending_jobs_now())
            except Exception:
                pass

        return job

    async def publish_to_instagram(
        self, publication_id: int, data: Any
    ) -> SportPublication:
        """Publie une publication validée sur Instagram via l'API Meta."""
        from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
        from app.services.sport_media_publish import MediaPublishService

        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")
        # Charger le contexte calendrier pour détecter les publications sportives
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        # Publications sportives : overlay stats (durée, dénivelé, km) + audio choisi automatiquement
        pub = await self._ensure_sport_defaults(pub)

        # Texte lisible : une réponse IA brute (JSON) ne doit jamais partir sur
        # Instagram. La correction est persistée par le commit ci-dessous.
        content = clean_caption_text(pub.content)
        if content and content != pub.content:
            pub.content = content
        hashtags = clean_hashtags(pub.hashtags)
        if hashtags and hashtags != pub.hashtags:
            pub.hashtags = hashtags

        # Auto-validation si la publication est encore en brouillon
        if pub.status == "draft":
            pub.status = "validated"
            pub.validated_at = datetime.now(timezone.utc)
            await self.db.commit()

        if pub.status not in ("validated", "draft"):
            raise ValueError("Seules les publications validées peuvent être publiées")

        if not (pub.content or "").strip():
            raise ValueError("Le contenu de la publication est vide")

        # Construire le caption complet (titre + accroche + hashtags)
        caption = build_full_caption(pub.title, pub.content, pub.hashtags)

        # Contrôle de longueur avant tout appel à l'API Meta ou à la base
        caption_length = len(caption)
        if caption_length > self.INSTAGRAM_CAPTION_MAX_LENGTH:
            raise ValueError(
                f"La légende Instagram dépasse la limite de "
                f"{self.INSTAGRAM_CAPTION_MAX_LENGTH} caractères "
                f"(actuellement {caption_length}). "
                f"Raccourcissez le texte ou les hashtags avant de publier."
            )

        # Vérifier qu'il y a un visuel
        if not pub.photo_id and not pub.visual_generation_prompt:
            raise ValueError("Un visuel est requis pour la publication Instagram")

        # Récupérer l'athlète associé à l'utilisateur
        athlete = await self.pub_service.get_or_create_athlete()

        # Source de publication : configuration Meta centralisée (jeton SUAT)
        meta_service = MetaPublishService(self.db)
        connection = await meta_service.resolve_publish_context()
        if not connection:
            raise ValueError(
                "Aucune source de publication Instagram configurée. "
                "Connectez votre compte Meta ou renseignez la configuration Meta."
            )

        if not connection.instagram_business_account_id:
            raise ValueError("Compte Instagram Business non configuré")

        # Marquer comme "en cours de publication"
        pub.status = "publishing"
        await self.db.commit()

        try:
            # Préparer l'URL du média
            media_publish_service = MediaPublishService(self.db)
            media_url = None
            media_info = None
            is_video = pub.visual_type in ("reel", "video")

            if pub.photo_id:
                # Préparer l'URL publique du média (taille originale pour Meta)
                media_service = MediaPublishService(self.db)
                media_info = await media_service.prepare_media_for_publish(
                    pub.photo_id, self.current_user.id, size="original"
                )
                media_url = media_info.url
                # Valider la cohérence entre le type visuel déclaré et le type MIME réel
                if media_info.is_video != is_video:
                    raise ValueError(
                        f"Incohérence de type de média : le visuel est une {'vidéo' if media_info.is_video else 'photo'} "
                        f"(MIME: {media_info.mime_type}) mais le type visuel déclaré est '{pub.visual_type}'. "
                        f"Sélectionnez le type de visuel correspondant dans le Studio."
                    )
            elif pub.visual_generation_prompt:
                # TODO: Génération d'image IA - pour l'instant erreur
                raise ValueError("La génération d'images IA n'est pas encore disponible. Sélectionnez une photo.")

            if not media_url:
                raise ValueError("Impossible de préparer le média pour publication")

            # Publier via Meta (contexte déjà résolu plus haut)
            try:
                is_reel = pub.visual_type == "reel"
                if pub.visual_type == "reel" or is_video:
                    instagram_media_id = await meta_service.publish_video(
                        connection, media_url, caption,
                        mime_type=media_info.mime_type if media_info else None,
                        is_reel=is_reel,
                        publication_id=publication_id,
                    )
                else:
                    instagram_media_id = await meta_service.publish_photo(
                        connection, media_url, caption,
                        mime_type=media_info.mime_type if media_info else None,
                        publication_id=publication_id,
                    )

                # Récupérer le permalink
                permalink = await meta_service.get_media_permalink(connection, instagram_media_id)

                # Marquer comme publiée avec succès
                pub.status = "shared"
                pub.shared_at = datetime.now(timezone.utc)
                pub.instagram_media_id = instagram_media_id
                pub.instagram_permalink = permalink
                pub.error_message = None

                # Mettre à jour le statut de l'entrée de calendrier après publication réussie
                entry = getattr(pub, "calendar_entry", None)
                if entry is not None:
                    entry.status = "publié"
                    await self.db.commit()
                    await self.db.refresh(pub)

                await self.db.commit()
                await self.db.refresh(pub)

                logger.info(f"Publication Instagram réussie: media_id={instagram_media_id}, publication_id={publication_id}")
                return pub

            except Exception as e:
                # En cas d'erreur, marquer comme échouée
                pub.status = "failed"
                pub.failed_at = datetime.now(timezone.utc)
                pub.error_message = str(e)
                await self.db.commit()
                await self.db.refresh(pub)

                logger.error(f"Erreur publication Instagram: {e}")
                raise ValueError(f"Échec de la publication Instagram: {str(e)}")

        except MetaPublishError as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = f"Meta API: {str(e)}"
            await self.db.commit()
            await self.db.refresh(pub)
            raise ValueError(f"Erreur Meta: {str(e)}")
        except Exception as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = str(e)
            await self.db.commit()
            await self.db.refresh(pub)
            logger.exception(f"Erreur publication Instagram: {e}")
            raise ValueError(f"Erreur de publication: {str(e)}")

    async def publish_to_facebook_page(
        self, publication_id: int, data: Any
    ) -> SportPublication:
        """Publie une publication validée sur une Page Facebook via l'API Meta."""
        from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
        from app.services.sport_media_publish import MediaPublishService

        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")
        # Charger le contexte calendrier pour détecter les publications sportives
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        # Publications sportives : overlay stats (durée, dénivelé, km) + audio choisi automatiquement
        pub = await self._ensure_sport_defaults(pub)

        # Texte lisible : une réponse IA brute (JSON) ne doit jamais partir sur
        # Facebook. La correction est persistée par le commit ci-dessous.
        content = clean_caption_text(pub.content)
        if content and content != pub.content:
            pub.content = content
        hashtags = clean_hashtags(pub.hashtags)
        if hashtags and hashtags != pub.hashtags:
            pub.hashtags = hashtags

        # Auto-validation si la publication est encore en brouillon
        if pub.status == "draft":
            pub.status = "validated"
            pub.validated_at = datetime.now(timezone.utc)
            await self.db.commit()

        if pub.status not in ("validated", "draft"):
            raise ValueError("Seules les publications validées peuvent être publiées")

        if not (pub.content or "").strip():
            raise ValueError("Le contenu de la publication est vide")

        # Construire le caption complet (titre + accroche + hashtags)
        caption = build_full_caption(pub.title, pub.content, pub.hashtags)

        # Contrôle de longueur avant tout appel à l'API Meta
        # Facebook n'a pas de limite stricte comme Instagram, mais on garde une limite raisonnable
        caption_length = len(caption)
        if caption_length > 2000:
            raise ValueError(
                f"La légende Facebook dépasse la limite de 2000 caractères "
                f"(actuellement {caption_length}). "
                f"Raccourcissez le texte ou les hashtags avant de publier."
            )

        # Vérifier qu'il y a un visuel
        if not pub.photo_id and not pub.visual_generation_prompt:
            raise ValueError("Un visuel est requis pour la publication Facebook")

        # Récupérer l'athlète associé à l'utilisateur
        athlete = await self.pub_service.get_or_create_athlete()

        # Source de publication : configuration Meta centralisée (jeton SUAT)
        meta_service = MetaPublishService(self.db)
        connection = await meta_service.resolve_facebook_publish_context()
        if not connection:
            raise ValueError(
                "Aucune source de publication Facebook Page configurée. "
                "Configurez l'ID de Page Facebook dans la configuration Meta."
            )

        if not connection.facebook_page_id:
            raise ValueError("ID de Page Facebook non configuré")

        # Marquer comme "en cours de publication"
        pub.status = "publishing"
        await self.db.commit()

        try:
            # Préparer l'URL du média
            media_publish_service = MediaPublishService(self.db)
            media_url = None
            media_info = None
            is_video = pub.visual_type in ("reel", "video")

            if pub.photo_id:
                # Préparer l'URL publique du média (taille originale pour Meta)
                media_service = MediaPublishService(self.db)
                media_info = await media_service.prepare_media_for_publish(
                    pub.photo_id, self.current_user.id, size="original"
                )
                media_url = media_info.url
                # Valider la cohérence entre le type visuel déclaré et le type MIME réel
                if media_info.is_video != is_video:
                    raise ValueError(
                        f"Incohérence de type de média : le visuel est une {'vidéo' if media_info.is_video else 'photo'} "
                        f"(MIME: {media_info.mime_type}) mais le type visuel déclaré est '{pub.visual_type}'. "
                        f"Sélectionnez le type de visuel correspondant dans le Studio."
                    )
            elif pub.visual_generation_prompt:
                # TODO: Génération d'image IA - pour l'instant erreur
                raise ValueError("La génération d'images IA n'est pas encore disponible. Sélectionnez une photo.")

            if not media_url:
                raise ValueError("Impossible de préparer le média pour publication")

            # Publier via Meta (contexte Facebook Page)
            try:
                is_reel = pub.visual_type == "reel"
                if pub.visual_type == "reel" or is_video:
                    facebook_media_id = await meta_service.publish_to_facebook_page(
                        connection, media_url, caption,
                        mime_type=media_info.mime_type if media_info else None,
                        is_video=is_video,
                        publication_id=publication_id,
                    )
                else:
                    facebook_media_id = await meta_service.publish_to_facebook_page(
                        connection, media_url, caption,
                        mime_type=media_info.mime_type if media_info else None,
                        is_video=False,
                        publication_id=publication_id,
                    )

                # Récupérer le permalink
                permalink = await meta_service.get_facebook_media_permalink(connection, facebook_media_id)

                # Marquer comme publiée avec succès
                pub.status = "shared"
                pub.shared_at = datetime.now(timezone.utc)
                pub.facebook_media_id = facebook_media_id
                pub.facebook_permalink = permalink
                pub.error_message = None

                await self.db.commit()
                await self.db.refresh(pub)

                logger.info(f"Publication Facebook Page réussie: media_id={facebook_media_id}, publication_id={publication_id}")
                return pub

            except Exception as e:
                pub.status = "failed"
                pub.failed_at = datetime.now(timezone.utc)
                pub.error_message = str(e)
                await self.db.commit()
                await self.db.refresh(pub)
                logger.error(f"Erreur publication Facebook Page: {e}")
                raise ValueError(f"Échec de la publication Facebook Page: {str(e)}")

        except MetaPublishError as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = f"Meta API: {str(e)}"
            await self.db.commit()
            await self.db.refresh(pub)
            raise ValueError(f"Erreur Meta: {str(e)}")
        except Exception as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = str(e)
            await self.db.commit()
            await self.db.refresh(pub)
            logger.exception(f"Erreur publication Facebook Page: {e}")
            raise ValueError(f"Erreur de publication: {str(e)}")

    async def publish_to_both(
        self, publication_id: int, data: Any
    ) -> SportPublication:
        """Publie une publication validée sur Instagram ET Facebook Page simultanément."""
        from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
        from app.services.sport_media_publish import MediaPublishService

        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")
        # Charger le contexte calendrier
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        pub = await self._ensure_sport_defaults(pub)

        # Nettoyage du contenu
        content = clean_caption_text(pub.content)
        if content and content != pub.content:
            pub.content = content
        hashtags = clean_hashtags(pub.hashtags)
        if hashtags and hashtags != pub.hashtags:
            pub.hashtags = hashtags

        # Auto-validation si brouillon
        if pub.status == "draft":
            pub.status = "validated"
            pub.validated_at = datetime.now(timezone.utc)
            await self.db.commit()

        if pub.status not in ("validated", "draft"):
            raise ValueError("Seules les publications validées peuvent être publiées")

        if not (pub.content or "").strip():
            raise ValueError("Le contenu de la publication est vide")

        # Construire le caption complet (titre + accroche + hashtags)
        caption = build_full_caption(pub.title, pub.content, pub.hashtags)

        # Contrôle de longueur (limite Instagram = 2200)
        caption_length = len(caption)
        if caption_length > 2200:
            raise ValueError(
                f"La légende dépasse la limite Instagram de 2200 caractères "
                f"(actuellement {caption_length}). Raccourcissez le texte."
            )

        # Vérifier visuel
        if not pub.photo_id and not pub.visual_generation_prompt:
            raise ValueError("Un visuel est requis pour la publication")

        # Récupérer l'athlète
        athlete = await self.pub_service.get_or_create_athlete()

        # Résoudre les DEUX contextes de publication
        meta_service = MetaPublishService(self.db)
        
        # Contexte Instagram
        ig_connection = await meta_service.resolve_publish_context()
        if not ig_connection or not ig_connection.instagram_business_account_id:
            raise ValueError(
                "Aucune source de publication Instagram configurée. "
                "Configurez le compte Instagram Business dans la configuration Meta."
            )
        
        # Contexte Facebook
        fb_connection = await meta_service.resolve_facebook_publish_context()
        if not fb_connection or not fb_connection.facebook_page_id:
            raise ValueError(
                "Aucune source de publication Facebook Page configurée. "
                "Configurez l'ID de Page Facebook dans la configuration Meta."
            )

        # Marquer comme "en cours de publication"
        pub.status = "publishing"
        await self.db.commit()

        try:
            # Préparer l'URL du média : un token Meta à usage unique est consommé par
            # plateforme, il faut donc un token distinct par cible (Instagram / Facebook).
            media_publish_service = MediaPublishService(self.db)
            media_url = None
            media_info = None
            media_infos: dict = {}
            is_video = pub.visual_type in ("reel", "video")

            if pub.photo_id:
                media_service = MediaPublishService(self.db)
                media_infos["instagram"] = await media_service.prepare_media_for_publish(
                    pub.photo_id, self.current_user.id, size="original"
                )
                media_infos["facebook"] = await media_service.prepare_media_for_publish(
                    pub.photo_id, self.current_user.id, size="original"
                )
            elif pub.visual_generation_prompt:
                raise ValueError("La génération d'images IA n'est pas encore disponible. Sélectionnez une photo.")

            if not media_infos:
                raise ValueError("Impossible de préparer le média pour publication")

            ig_media_info = media_infos["instagram"]
            fb_media_info = media_infos["facebook"]
            media_info = ig_media_info
            media_url = ig_media_info.url
            if ig_media_info.is_video != is_video:
                raise ValueError(
                    f"Incohérence de type de média : le visuel est une {'vidéo' if ig_media_info.is_video else 'photo'} "
                    f"(MIME: {ig_media_info.mime_type}) mais le type visuel déclaré est '{pub.visual_type}'."
                )

            # Publier sur LES DEUX plateformes
            try:
                is_reel = pub.visual_type == "reel"
                results = {}
                
                # Publication Instagram
                try:
                    if pub.visual_type == "reel" or is_video:
                        ig_media_id = await meta_service.publish_video(
                            ig_connection, media_url, caption,
                            mime_type=media_info.mime_type if media_info else None,
                            is_reel=is_reel,
                            publication_id=publication_id,
                        )
                    else:
                        ig_media_id = await meta_service.publish_photo(
                            ig_connection, media_url, caption,
                            mime_type=media_info.mime_type if media_info else None,
                            publication_id=publication_id,
                        )
                    ig_permalink = await meta_service.get_media_permalink(ig_connection, ig_media_id)
                    results['instagram'] = {'media_id': ig_media_id, 'permalink': ig_permalink}
                    logger.info(f"Publication Instagram réussie: media_id={ig_media_id}")
                except Exception as e:
                    logger.error(f"Échec publication Instagram: {e}")
                    results['instagram'] = {'error': str(e)}
                
                # Publication Facebook
                try:
                    fb_media_id = await meta_service.publish_to_facebook_page(
                        fb_connection, fb_media_info.url, caption,
                        mime_type=fb_media_info.mime_type if fb_media_info else None,
                        is_video=is_video,
                        publication_id=publication_id,
                    )
                    fb_permalink = await meta_service.get_facebook_media_permalink(fb_connection, fb_media_id)
                    results['facebook'] = {'media_id': fb_media_id, 'permalink': fb_permalink}
                    logger.info(f"Publication Facebook Page réussie: media_id={fb_media_id}")
                except Exception as e:
                    logger.error(f"Échec publication Facebook: {e}")
                    results['facebook'] = {'error': str(e)}
                
                # Déterminer le statut final
                ig_success = 'instagram' in results and 'error' not in results['instagram']
                fb_success = 'facebook' in results and 'error' not in results['facebook']

                # Mettre à jour le statut de l'entrée de calendrier après publication réussie
                if ig_success or fb_success:
                    entry = getattr(pub, "calendar_entry", None)
                    if entry is not None:
                        entry.status = "publié"
                        await self.db.commit()
                        await self.db.refresh(pub)
                
                if ig_success and fb_success:
                    pub.status = "shared"
                    pub.error_message = None
                elif ig_success or fb_success:
                    pub.status = "shared"
                    errors = []
                    if 'instagram' in results and 'error' in results['instagram']:
                        errors.append(f"Instagram: {results['instagram']['error']}")
                    if 'facebook' in results and 'error' in results['facebook']:
                        errors.append(f"Facebook: {results['facebook']['error']}")
                    pub.error_message = "Publication partielle - " + " | ".join(errors)
                else:
                    pub.status = "failed"
                    errors = []
                    if 'instagram' in results and 'error' in results['instagram']:
                        errors.append(f"Instagram: {results['instagram']['error']}")
                    if 'facebook' in results and 'error' in results['facebook']:
                        errors.append(f"Facebook: {results['facebook']['error']}")
                    pub.error_message = "Échec complet - " + " | ".join(errors)
                
                if ig_success:
                    pub.instagram_media_id = results['instagram']['media_id']
                    pub.instagram_permalink = results['instagram']['permalink']
                if fb_success:
                    pub.facebook_media_id = results['facebook']['media_id']
                    pub.facebook_permalink = results['facebook']['permalink']
                
                pub.shared_at = datetime.now(timezone.utc)
                await self.db.commit()
                await self.db.refresh(pub)
                logger.info(f"Publication multi-plateforme: IG={ig_success}, FB={fb_success}")
                return pub

            except Exception as e:
                pub.status = "failed"
                pub.failed_at = datetime.now(timezone.utc)
                pub.error_message = str(e)
                await self.db.commit()
                await self.db.refresh(pub)
                logger.error(f"Erreur publication multi-plateforme: {e}")
                raise ValueError(f"Échec de la publication: {str(e)}")

        except MetaPublishError as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = f"Meta API: {str(e)}"
            await self.db.commit()
            await self.db.refresh(pub)
            raise ValueError(f"Erreur Meta: {str(e)}")
        except Exception as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = str(e)
            await self.db.commit()
            await self.db.refresh(pub)
            logger.exception(f"Erreur publication multi-plateforme: {e}")
            raise ValueError(f"Erreur de publication: {str(e)}")

    async def get_suggested_photos(self, publication_id: int, limit: int = 15) -> list[dict[str, Any]]:
        """Récupère des photos suggérées pour la publication en reliant activités Garmin et dates."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")

        athlete, _ = await self._get_athlete_and_strategy()

        # Récupérer les activités récentes de l'athlète
        act_res = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id)
            .order_by(SportActivity.started_at.desc())
            .limit(15)
        )
        recent_acts = act_res.scalars().all()
        activity_dates: dict[Any, str] = {}
        for act in recent_acts:
            if act.started_at:
                activity_dates[act.started_at.date()] = act.activity_name or act.sport_type or "Activité Garmin"

        target_date = None
        if pub.calendar_entry_id:
            entry_res = await self.db.execute(
                select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == pub.calendar_entry_id)
            )
            entry = entry_res.scalar_one_or_none()
            if entry and entry.date:
                target_date = entry.date

        # Récupérer les photos de l'utilisateur
        photos_res = await self.db.execute(
            select(Photo)
            .where(
                Photo.owner_id == self.current_user.id,
                Photo.is_deleted.is_(False),
                Photo.status != "failed",
            )
            .order_by(Photo.taken_at.desc())
            .limit(40)
        )
        photos = photos_res.scalars().all()

        results = []
        for photo in photos:
            p_date = photo.taken_at.date() if photo.taken_at else None
            match_reason = "Photo récente"
            badge_class = "info"

            if target_date and p_date == target_date:
                match_reason = "Jour de la publication"
                badge_class = "primary"
            elif p_date and p_date in activity_dates:
                match_reason = f"Activité : {activity_dates[p_date]}"
                badge_class = "success"
            elif photo.is_favorite:
                match_reason = "Photo favorite"
                badge_class = "warning"

            results.append({
                "id": photo.id,
                "title": photo.title or photo.original_filename,
                "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
                "thumbnail_url": f"/photos/{photo.id}/file?size=small",
                "preview_url": f"/photos/{photo.id}/file?size=large",
                "match_reason": match_reason,
                "badge_class": badge_class,
                "is_current": (pub.photo_id == photo.id),
            })
            if len(results) >= limit:
                break

        return results