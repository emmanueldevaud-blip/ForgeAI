"""Service Studio Community Manager V2 - Création intelligente de publications."""

import asyncio
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
    PublicationDraftCreateRequest,
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

# Lot 1 / A05 : le format carrousel est sélectionnable dans le Publisher mais
# Meta ne reçoit actuellement qu'une seule photo (pas de conteneur album).
# Tant que `media_type=CAROUSEL` / `children` n'est pas implémenté et validé,
# la publication est bloquée avec un message explicite plutôt que de laisser
# croire à un carrousel publié.
CAROUSEL_PUBLISH_BLOCKED_MESSAGE = (
    "Le format carrousel ne peut pas encore être publié : Meta recevrait une seule photo "
    "au lieu des albums. Choisissez une photo unique, ou attendez l'implémentation du "
    "conteneur album (media_type=CAROUSEL, children)."
)


def build_full_caption(title: Optional[str], content: Optional[str], hashtags: Optional[str]) -> str:
    """Construit la légende Instagram complète : titre + hashtags.
    
    Format (nouveau) :
    [TITRE]
    
    [HASHTAGS]
    
    L'accroche (content) n'est plus dans la légende - elle est affichée sur la photo via l'overlay.
    
    Règles :
    - Supprime les champs vides
    - Pas de doublons d'espaces/retours à la ligne
    - Préserve les emojis et accents
    """
    parts = []
    if title and title.strip():
        parts.append(title.strip())
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


def _render_sport_stats_panel_html(stats: dict[str, str], style: str | None = None) -> str:
    """Panneau semi-transparent de stats pour l'aperçu HTML (miroir de l'overlay publié)."""
    if not stats:
        return ""
    top = []
    if stats.get("distance"):
        top.append(("DISTANCE", stats["distance"]))
    if stats.get("duree"):
        top.append(("TEMPS", stats["duree"]))
    bottom = []
    if stats.get("denivele"):
        bottom.append(("DÉNIVELÉ", stats["denivele"]))
    if not top and not bottom:
        return ""

    def cell(label: str, value: str) -> str:
        return (
            '<div style="text-align:center;">'
            f'<div style="font-size:9px; letter-spacing:1px; opacity:.85;">{label}</div>'
            f'<div style="font-size:15px; font-weight:700; line-height:1.2;">{value}</div>'
            "</div>"
        )

    rows = ""
    if top:
        rows += f'<div style="display:flex; gap:24px; justify-content:center;">{"".join(cell(l, v) for l, v in top)}</div>'
    if bottom:
        rows += f'<div style="display:flex; gap:24px; justify-content:center; margin-top:6px;">{"".join(cell(l, v) for l, v in bottom)}</div>'
    backgrounds = {
        "humour": "rgba(124,58,237,.86)",
        "aventure": "rgba(3,105,161,.86)",
        "performance": "rgba(0,0,0,0.72)",
        "souvenir": "rgba(120,53,15,.84)",
    }
    background = backgrounds.get(str(style).lower()) if style else "rgba(0,0,0,0.72)"
    return (
        '<div style="position:absolute; left:50%; bottom:16px; transform:translateX(-50%); '
        f"background:{background}; color:#ffffff; padding:10px 18px; border-radius:12px; "
        f'font-family:Arial, sans-serif; text-align:center; max-width:92%;">{rows}'
        '<div style="font-size:9px; opacity:.8; margin-top:6px;">#Jepepagtrail</div></div>'
    )


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


def _moving_time_seconds(activity: SportActivity | None) -> int | None:
    """Retourne le temps Garmin en mouvement, avec repli explicite.

    Garmin expose généralement ``movingDuration`` dans le résumé. Les
    anciennes importations conservent le résumé complet dans metadata_json.
    ``duration_seconds`` reste le repli des activités historiques dépourvues
    de cette information.
    """
    if activity is None:
        return None
    metadata = getattr(activity, "metadata_json", None) or {}
    summary = metadata.get("garmin_summary") if isinstance(metadata, dict) else None
    if not isinstance(summary, dict):
        summary = metadata if isinstance(metadata, dict) else {}
    for key in ("movingDuration", "movingTimeSeconds", "moving_time_seconds", "moving_time"):
        value = summary.get(key)
        if value is not None:
            try:
                value = int(float(value))
                if value > 0:
                    return value
            except (TypeError, ValueError):
                pass
    return int(activity.duration_seconds) if activity.duration_seconds else None


def _sport_location_hashtag(activity: SportActivity | None) -> str | None:
    """Construit le hashtag du lieu depuis les métadonnées Garmin disponibles."""
    if activity is None:
        return None
    metadata = getattr(activity, "metadata_json", None) or {}
    summary = metadata.get("garmin_summary") if isinstance(metadata, dict) else None
    if not isinstance(summary, dict):
        summary = metadata if isinstance(metadata, dict) else {}
    candidates = [
        summary.get("locationName"), summary.get("location"), summary.get("city"),
        (summary.get("startLocation") or {}).get("city") if isinstance(summary.get("startLocation"), dict) else None,
        (summary.get("endLocation") or {}).get("city") if isinstance(summary.get("endLocation"), dict) else None,
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            slug = re.sub(r"[^\wÀ-ÿ]+", "", value.strip(), flags=re.UNICODE)
            if slug:
                return f"#{slug}"
    return None


def _garmin_caption(activity: SportActivity | None, title: str | None) -> tuple[str, str]:
    """Légende Garmin minimale : titre exact, lieu, trailrunning."""
    caption_title = (title or getattr(activity, "activity_name", None) or "Sortie trail").strip()
    location = _sport_location_hashtag(activity)
    hashtags = " ".join(item for item in (location, "#trailrunning") if item)
    return caption_title, hashtags


def _ensure_garmin_hashtag(value: str | None) -> str:
    """Ajoute le hashtag de marque aux hashtags d'une publication Garmin."""
    text = (value or "").strip()
    if not re.search(r"(?<!\w)#jepepagtrail\b", text, re.IGNORECASE):
        text = f"{text} #jepepagtrail".strip()
    return text


def _sport_stats_from_activity(activity: SportActivity | None) -> dict[str, str]:
    if activity is None:
        return {}
    stats: dict[str, str] = {}
    if getattr(activity, "distance_m", None) is not None:
        stats["distance"] = f"{activity.distance_m / 1000:.1f} km"
    if getattr(activity, "elevation_gain_m", None) is not None:
        stats["denivele"] = f"{int(activity.elevation_gain_m)} m D+"
    dur = _format_duration(_moving_time_seconds(activity))
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


def render_sport_overlay_image(photo_path: str, stats: dict[str, str], out_path: str, title: str | None = None, style: str | None = None) -> str | None:
    """Compose les statistiques sportives (distance, temps, dénivelé) sur la photo.
    
    Layout adaptatif selon l'orientation :
    - Portrait: panneau en bas, stats empilées
    - Paysage: panneau en bas à droite, stats en deux lignes
    - Carré: panneau centré en bas
    
    Si title est fourni, il est affiché en haut de la photo.
    
    Retourne out_path ou None en cas d'erreur.
    """
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

        # Tailles de police adaptatives
        base_font_size = max(int(min(w, h) * 0.035), 20)
        font_label = load_font(max(base_font_size // 2, 14))
        font_value = load_font(base_font_size)
        font_signature = load_font(max(base_font_size // 3, 12))
        font_title = load_font(max(int(min(w, h) * 0.05), 24))

        # Extraire les stats dans l'ordre souhaité
        distance = stats.get("distance")
        duree = stats.get("duree")
        denivele = stats.get("denivele")

        # Construire les lignes de texte
        top_items = []
        if distance:
            top_items.append(("DISTANCE", distance))
        if duree:
            top_items.append(("TEMPS", duree))
        
        bottom_items = []
        if denivele:
            bottom_items.append(("DÉNIVELÉ", denivele))

        # Mesurer les dimensions du texte
        def measure_text(text, font):
            try:
                bbox = draw.textbbox((0, 0), text, font=font)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except Exception:
                return len(text) * (font.size // 2), font.size

        # Calculer les dimensions du panneau
        padding = max(int(min(w, h) * 0.025), 20)
        gap_x = max(int(w * 0.03), 30)
        gap_y = max(int(h * 0.015), 12)
        
        # Mesurer les éléments du haut
        top_widths = []
        top_heights = []
        for label, value in top_items:
            lw, lh = measure_text(label, font_label)
            vw, vh = measure_text(value, font_value)
            top_widths.append(max(lw, vw))
            top_heights.append(lh + vh + gap_y)
        
        # Mesurer les éléments du bas
        bottom_widths = []
        bottom_heights = []
        for label, value in bottom_items:
            lw, lh = measure_text(label, font_label)
            vw, vh = measure_text(value, font_value)
            bottom_widths.append(max(lw, vw))
            bottom_heights.append(lh + vh + gap_y)

        # Signature
        sig_text = "#Jepepagtrail"
        sig_w, sig_h = measure_text(sig_text, font_signature)

        # Déterminer la position et taille du panneau selon l'orientation
        is_portrait = h > w * 1.2
        is_landscape = w > h * 1.2
        
        if is_portrait:
            # Portrait: panneau en bas, centré, stats empilées
            panel_w = min(w - 2 * padding, max(sum(top_widths) + gap_x * (len(top_items) - 1), max(bottom_widths) if bottom_widths else 0, sig_w) + 2 * padding)
            top_h = max(top_heights) if top_heights else 0
            bottom_h = max(bottom_heights) if bottom_heights else 0
            panel_h = top_h + (gap_y if top_items and bottom_items else 0) + bottom_h + sig_h + gap_y + 2 * padding
            panel_x = (w - panel_w) // 2
            panel_y = h - panel_h - max(int(h * 0.05), 40)
        elif is_landscape:
            # Paysage: panneau en bas à droite
            panel_w = min(w * 0.55, max(sum(top_widths) + gap_x * (len(top_items) - 1), max(bottom_widths) if bottom_widths else 0, sig_w) + 2 * padding)
            top_h = max(top_heights) if top_heights else 0
            bottom_h = max(bottom_heights) if bottom_heights else 0
            panel_h = top_h + (gap_y if top_items and bottom_items else 0) + bottom_h + sig_h + gap_y + 2 * padding
            panel_x = w - panel_w - max(int(w * 0.05), 40)
            panel_y = h - panel_h - max(int(h * 0.05), 40)
        else:
            # Carré: panneau centré en bas
            panel_w = min(w - 2 * padding, max(sum(top_widths) + gap_x * (len(top_items) - 1), max(bottom_widths) if bottom_widths else 0, sig_w) + 2 * padding)
            top_h = max(top_heights) if top_heights else 0
            bottom_h = max(bottom_heights) if bottom_heights else 0
            panel_h = top_h + (gap_y if top_items and bottom_items else 0) + bottom_h + sig_h + gap_y + 2 * padding
            panel_x = (w - panel_w) // 2
            panel_y = h - panel_h - max(int(h * 0.05), 40)

        # Dessiner le titre en haut de la photo si fourni
        if title:
            # Mesurer le titre
            title_lines = []
            words = title.split()
            current_line = ""
            max_title_width = w - 2 * padding
            
            for word in words:
                test_line = current_line + (" " if current_line else "") + word
                tw, th = measure_text(test_line, font_title)
                if tw <= max_title_width:
                    current_line = test_line
                else:
                    if current_line:
                        title_lines.append(current_line)
                    current_line = word
            if current_line:
                title_lines.append(current_line)
            
            # Dessiner chaque ligne du titre avec ombre
            title_y = padding
            for line in title_lines:
                tw, th = measure_text(line, font_title)
                title_x = (w - tw) // 2
                # Ombre
                draw.text((title_x + 2, title_y + 2), line, fill=(0, 0, 0, 200), font=font_title)
                # Texte principal
                draw.text((title_x, title_y), line, fill=(255, 255, 255, 255), font=font_title)
                title_y += th + 4

        palette = {
            "humour": ((124, 58, 237, 218), (255, 255, 255, 255), (237, 233, 254, 255)),
            "aventure": ((3, 105, 161, 218), (255, 255, 255, 255), (186, 230, 253, 255)),
            "performance": ((0, 0, 0, 180), (255, 255, 255, 255), (200, 200, 200, 255)),
            "souvenir": ((120, 53, 15, 210), (255, 255, 255, 255), (254, 215, 170, 255)),
            # Noms Quick Reel : conserver les palettes historiques du moteur.
            "cinematique": ((3, 105, 161, 218), (255, 255, 255, 255), (186, 230, 253, 255)),
            "dynamique": ((0, 0, 0, 180), (255, 255, 255, 255), (200, 200, 200, 255)),
        }
        panel_color, value_color, label_color = palette.get(str(style or "performance").lower(), palette["performance"])

        # Dessiner le fond semi-transparent du panneau
        corner_radius = max(int(min(w, h) * 0.015), 12)
        draw.rounded_rectangle(
            [(panel_x, panel_y), (panel_x + panel_w, panel_y + panel_h)],
            radius=corner_radius,
            fill=panel_color
        )

        # Position de départ pour le contenu
        content_x = panel_x + padding
        content_y = panel_y + padding
        current_y = content_y

        # Dessiner la ligne du haut (Distance, Temps)
        if top_items:
            total_top_w = sum(top_widths) + gap_x * (len(top_items) - 1)
            start_x = panel_x + (panel_w - total_top_w) // 2
            for i, (label, value) in enumerate(top_items):
                item_w = top_widths[i]
                item_x = start_x + i * (top_widths[i-1] + gap_x) if i > 0 else start_x
                
                lw, lh = measure_text(label, font_label)
                vw, vh = measure_text(value, font_value)
                
                label_x = item_x + (item_w - lw) // 2
                value_x = item_x + (item_w - vw) // 2
                
                draw.text((label_x, current_y), label, fill=label_color, font=font_label)
                draw.text((value_x, current_y + lh + 2), value, fill=value_color, font=font_value)
            
            current_y += max(top_heights) + gap_y

        # Dessiner la ligne du bas (Dénivelé)
        if bottom_items:
            for label, value in bottom_items:
                lw, lh = measure_text(label, font_label)
                vw, vh = measure_text(value, font_value)
                
                label_x = panel_x + (panel_w - lw) // 2
                value_x = panel_x + (panel_w - vw) // 2
                
                draw.text((label_x, current_y), label, fill=label_color, font=font_label)
                draw.text((value_x, current_y + lh + 2), value, fill=value_color, font=font_value)
            
            current_y += max(bottom_heights) + gap_y

        # Dessiner la signature
        sig_x = panel_x + (panel_w - sig_w) // 2
        draw.text((sig_x, current_y), sig_text, fill=label_color, font=font_signature)

        # Composer l'image finale
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
    # Attente max (s) du rendu vidéo compagnon pendant une publication.
    COMPANION_READY_WAIT_SECONDS: float = 90.0

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

        # Les deux usages audio sont distincts : ``ig_audio`` est une référence
        # Meta (non téléchargeable par ForgeAI), ``audio`` est la piste locale
        # vérifiée que le moteur FFmpeg peut réellement intégrer. Initialiser la
        # piste locale ici évite qu'un brouillon créé depuis le calendrier affiche
        # une musique sélectionnée alors que le rendu n'a aucune source audio.
        if _is_sport_publication(publication):
            publication = await self._ensure_sport_defaults(publication, persist_overlay=False)
            if data.photo_id:
                publication = await self._refresh_ig_music(publication)
            await self.db.commit()
            await self.db.refresh(publication)

        return publication

    async def create_standalone_draft(
        self, data: PublicationDraftCreateRequest
    ) -> SportPublication:
        """Crée un brouillon standalone (sans entrée de calendrier, sans activité).

        Lot 0 (A01) : permet à un utilisateur de créer une publication depuis
        zéro (bibliothèque photos) et d'atteindre un état « sauvegardable » puis
        « publishable » côté Studio/Publisher, sans passer par une entrée de
        calendrier ou une activité Garmin.
        """
        athlete, _strategy = await self._get_athlete_and_strategy()
        publication = SportPublication(
            athlete_id=athlete.id,
            status="draft",
            created_from="standalone",
            visual_type=data.visual_type or "photo",
            title=data.title,
            content=data.content,
            hashtags=data.hashtags,
            photo_id=data.photo_id,
            styles=data.styles or [],
        )
        self.db.add(publication)
        await self.db.flush()
        await self.db.commit()
        # `created_at`/`updated_at` ont un server_default SQL : après le flush,
        # SQLAlchemy les laisse expirés pour les relire en base. La session étant
        # en `expire_on_commit=False`, un commit ne les recharge pas. Sans ce
        # refresh, la validation Pydantic de PublicationDraftResponse accède à
        # ces attributs en synchrone et déclenche MissingGreenlet (422).
        await self.db.refresh(publication)
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
                    design["elements"] = [
                        element for element in (design.get("elements") or [])
                        if not (isinstance(element, dict) and element.get("type") == "sport_stats")
                    ] + new_stats
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

        # Publication déjà partagée : lecture seule (aucune modification).
        if pub.status == "shared":
            raise ValueError("Cette publication est déjà publiée et ne peut plus être modifiée.")

        # Vérifier que l'utilisateur a le droit (déjà fait par get_publication)

        # Mettre à jour les champs fournis (texte/hashtags/titre toujours modifiables
        # pour stories et publications sportives, sauf publication partagée gérée côté statut/UI)
        if data.title is not None:
            pub.title = data.title
        if data.content is not None:
            pub.content = data.content
        if data.hashtags is not None:
            pub.hashtags = data.hashtags
        if "photo_ids" in data.model_fields_set and not pub.photo_locked:
            ids = await self._validate_photo_ids(data.photo_ids or [])
            design = dict(pub.design) if isinstance(pub.design, dict) else {}
            previous_ids = design.get("carousel") or ([pub.photo_id] if pub.photo_id else [])
            try:
                previous_ids = [int(x) for x in previous_ids]
            except (TypeError, ValueError):
                previous_ids = []
            photos_changed = ids != previous_ids
            if ids:
                design["carousel"] = ids
                pub.photo_id = ids[0]
            else:
                design.pop("carousel", None)
                pub.photo_id = None
            pub.design = design
            if _is_sport_publication(pub):
                pub = await self._ensure_sport_defaults(pub, persist_overlay=False)
                # Rechoisir la musique uniquement si la sélection photo change :
                # renvoyer les mêmes photo_ids (publication) ne doit pas remplacer
                # une musique déjà choisie par l'utilisateur.
                if photos_changed:
                    pub = await self._refresh_ig_music(pub)
        if "photo_id" in data.model_fields_set:
            if not pub.photo_locked and "photo_ids" not in data.model_fields_set:
                previous_photo_id = pub.photo_id
                pub.photo_id = data.photo_id
                # Sélection mono-photo : le carrousel reflète la sélection unique
                design = dict(pub.design) if isinstance(pub.design, dict) else {}
                if data.photo_id is None:
                    design.pop("carousel", None)
                else:
                    design["carousel"] = [data.photo_id]
                pub.design = design
                # Déclencher la composition automatique de l'overlay sport
                # si c'est une publication sportive (Garmin) — rendu visuel uniquement,
                # sans enregistrement dans le module photo (réservé à la publication)
                if _is_sport_publication(pub):
                    pub = await self._ensure_sport_defaults(pub, persist_overlay=False)
                    # Musique Instagram : (re)choix par IA (vision) uniquement
                    # quand la couverture change ; nettoyage si la photo est retirée.
                    if previous_photo_id != data.photo_id:
                        pub = await self._refresh_ig_music(pub)
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

        if data.quick_generation and _is_sport_publication(pub):
            await self.ensure_companion_video_job(pub, force=True)

        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def _refresh_ig_music(self, pub: SportPublication) -> SportPublication:
        """(Re)choisit la musique Instagram à partir de la photo de couverture.

        Analyse vision de la photo de couverture (premier du carrousel si multi)
        + titre -> recherche dans le catalogue Instagram (ig_audio)
        -> persistance dans design["ig_audio"].
        Échec non bloquant : le choix précédent est conservé.
        """
        if not _is_sport_publication(pub):
            return pub

        design = pub.design if isinstance(pub.design, dict) else {}
        
        # Déterminer la photo de couverture : premier du carrousel ou photo unique
        carousel = design.get("carousel") if isinstance(design.get("carousel"), list) else None
        cover_photo_id = None
        if carousel:
            try:
                cover_photo_id = int(carousel[0])
            except (TypeError, ValueError, IndexError):
                pass
        if not cover_photo_id:
            cover_photo_id = pub.photo_id
        
        if not cover_photo_id:
            # Photo(s) retirée(s) : la musique associée n'a plus de sens
            if "ig_audio" in design:
                design = dict(design)
                design.pop("ig_audio", None)
                pub.design = design
            return pub

        from app.services.community_manager.ig_music import pick_audio_for_photo_bounded
        import inspect
        
        previous_audio_id = design.get("ig_audio", {}).get("audio_id") if isinstance(design.get("ig_audio"), dict) else None
        audio_kwargs = {"title": pub.title, "hashtags": pub.hashtags}
        if previous_audio_id:
            try:
                sig = inspect.signature(pick_audio_for_photo_bounded)
                if "avoid_audio_id" in sig.parameters or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                ):
                    audio_kwargs["avoid_audio_id"] = str(previous_audio_id)
            except (ValueError, TypeError):
                pass

        try:
            entry = await pick_audio_for_photo_bounded(
                self.db,
                self.current_user,
                cover_photo_id,
                **audio_kwargs,
            )
        except Exception:
            logger.exception(
                "[CM-STUDIO] Choix musique IG impossible pour la publication %s", pub.id
            )
            return pub
        
        if entry:
            design = dict(pub.design) if isinstance(pub.design, dict) else {}
            design["ig_audio"] = entry
            pub.design = design
        else:
            # Ne jamais laisser croire que l'ancienne musique correspond encore
            # à la nouvelle photo si l'analyse IA n'a pas abouti.
            design = dict(pub.design) if isinstance(pub.design, dict) else {}
            design.pop("ig_audio", None)
            pub.design = design
        return pub

    async def _validate_photo_ids(self, ids: list[int]) -> list[int]:
        """Filtre la sélection multi-photos : max 10, sans doublons, accessibles."""
        cleaned: list[int] = []
        for raw in ids or []:
            try:
                pid = int(raw)
            except (TypeError, ValueError):
                continue
            if pid in cleaned or len(cleaned) >= 10:
                continue
            photo = await self.db.get(Photo, pid)
            if photo is None or photo.is_deleted:
                continue
            if photo.owner_id != self.current_user.id and not photo.is_public:
                continue
            cleaned.append(pid)
        return cleaned

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

    @staticmethod
    def assert_publishable_format(pub: SportPublication) -> None:
        """Lot 1 / A05 : bloque le carrousel avant toute validation/publication.

        Vérifie le type visuel déclaré et, pour les anciens brouillons sans type
        explicite, un design portant plusieurs photos. Les publications sportives
        Garmin (Reel) et les Stories ne sont pas concernées.
        """
        design = pub.design if isinstance(pub.design, dict) else {}
        carousel = design.get("carousel")
        visual_type = getattr(pub, "visual_type", None)
        is_carousel = visual_type == "carousel" or (
            visual_type in (None, "", "photo")
            and isinstance(carousel, list)
            and len(carousel) > 1
            and not _is_sport_publication(pub)
        )
        if is_carousel:
            raise ValueError(CAROUSEL_PUBLISH_BLOCKED_MESSAGE)

    async def validate_for_publication(
        self, publication_id: int, data: PublicationValidateRequest
    ) -> Optional[SportPublication]:
        """Valide un brouillon pour publication (passe en 'validated')."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None
        self.assert_publishable_format(pub)

        if pub.status == "shared":
            raise ValueError("Cette publication est déjà publiée.")

        if not (pub.content or "").strip() and not (_is_sport_publication(pub) and (pub.title or pub.hashtags)):
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
        """Planifie une publication validée (Lot 1 / A04 : non exposé).

        Conservé comme proposition pour un futur scheduler idempotent ;
        l'endpoint HTTP est désactivé tant qu'aucun worker ne consomme ce statut.
        """
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

        # Publications sportives : overlay stats (durée, dénivelé, km) et choix audio —
        # aucun enregistrement dans le module photo avant la publication
        if _is_sport_publication(pub):
            pub = await self._ensure_sport_defaults(pub, persist_overlay=False)
            await self.db.commit()
            await self.db.refresh(pub)

        # Rendu HTML simple pour prévisualisation
        content = clean_caption_text(pub.content) or ""
        hashtags = clean_hashtags(pub.hashtags) or ""
        title = pub.title or ""
        # Légende complète = titre + hashtags (même contenu que le champ éditable)
        full_caption = build_full_caption(title, content, hashtags)
        photo_url = None
        if pub.photo_id:
            # URL de fichier photo pour l'aperçu côté navigateur (authentification standard).
            # Ne pas utiliser de meta_token ici: les tokens de publication Meta sont à usage unique.
            photo_url = f"/photos/{pub.photo_id}/file?size=large"

        # Stats sportives visibles sur l'image : panneau sombre identique à celui
        # appliqué sur la photo au moment de la publication (jamais de texte blanc
        # posé directement sur le fond clair).
        stats_panel_html = ""
        if photo_url:
            activity = await self._get_activity_for_publication(pub)
            editorial = pub.design.get("editorial_engine") if isinstance(pub.design, dict) else {}
            stats_panel_html = _render_sport_stats_panel_html(
                _sport_stats_from_activity(activity),
                editorial.get("style") if isinstance(editorial, dict) else None,
            )

        # Ratio de l'image d'aperçu : issu du design (défaut 1080x1350).
        # Le conteneur s'adapte ainsi à tous les formats (portrait, carré, paysage).
        preview_design = pub.design if isinstance(pub.design, dict) else {}
        preview_fmt = preview_design.get("format") if isinstance(preview_design.get("format"), dict) else {}
        fmt_w = float(preview_fmt.get("width") or 0)
        fmt_h = float(preview_fmt.get("height") or 0)
        if not (0 < fmt_w <= 20000 and 0 < fmt_h <= 20000):
            fmt_w, fmt_h = 1080.0, 1350.0
        feed_ratio = f"{fmt_w:g}/{fmt_h:g}"

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
            <div style="max-width: 480px; background: var(--color-bg-primary, #fff); color: var(--color-text-primary, #111827); border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="padding: 12px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--color-border-light, #efefef);">
                    <div style="width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%);"></div>
                    <div>
                        <div style="font-weight: 600; font-size: 14px;">{self.current_user.username or 'Utilisateur'}</div>
                        <div style="font-size: 12px; color: var(--color-text-muted, #8e8e8e);">{datetime.now().strftime('%d/%m/%Y')}</div>
                    </div>
                </div>
                <div style="position: relative; width: 100%; aspect-ratio: {feed_ratio}; background: #111111;">
                    {f'<img src="{photo_url}" style="width: 100%; height: 100%; object-fit: cover;">' if photo_url else '<div style="width: 100%; height: 100%; background: var(--color-bg-tertiary, #fafafa); display: flex; align-items: center; justify-content: center; color: var(--color-text-muted, #999);">Aucune image</div>'}
                    {stats_panel_html}
                </div>
                <div style="padding: 12px 16px;">
                    <div style="font-size: 14px; line-height: 1.5; white-space: pre-wrap;">{full_caption}</div>
                </div>
                <div style="padding: 8px 16px; border-top: 1px solid var(--color-border-light, #efefef); display: flex; gap: 16px; color: var(--color-text-muted, #8e8e8e); font-size: 13px;">
                    <span>♥️ 0</span>
                    <span>💬 0</span>
                    <span>📤 0</span>
                </div>
            </div>
            """
        elif format == "story":
            html = f"""
            <div style="width: 100%; max-width: 420px; aspect-ratio: 9/16; margin: 0 auto; background: #000; position: relative; color: white; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                {f'<img src="{photo_url}" style="width: 100%; height: 100%; object-fit: cover;">' if photo_url else ''}
                {stats_panel_html}
                <div style="position: absolute; bottom: 24px; left: 16px; right: 16px; text-shadow: 0 2px 8px rgba(0,0,0,0.7);">
                    <div style="font-size: 16px; line-height: 1.4; white-space: pre-wrap;">{full_caption}</div>
                </div>
            </div>
            """
        elif format == "strategic":
            # Mode stratégique : léger, juste stats + accroche courte, pas de blabla
            # Extraire les stats si disponibles dans le contenu
            stats_html = self._extract_stats_html(content)
            html = f"""
            <div style="max-width: 480px; background: var(--color-bg-primary, #fff); color: var(--color-text-primary, #111827); border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <div style="padding: 12px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--color-border-light, #efefef);">
                    <div style="width: 32px; height: 32px; border-radius: 50%; background: linear-gradient(45deg, #f09433 0%,#e6683c 25%,#dc2743 50%,#cc2366 75%,#bc1888 100%);"></div>
                    <div>
                        <div style="font-weight: 600; font-size: 14px;">{self.current_user.username or 'Utilisateur'}</div>
                        <div style="font-size: 12px; color: var(--color-text-muted, #8e8e8e);">{datetime.now().strftime('%d/%m/%Y')}</div>
                    </div>
                </div>
                {f'<img src="{photo_url}" style="width: 100%; aspect-ratio: {feed_ratio}; object-fit: cover; display: block;">' if photo_url else f'<div style="width: 100%; aspect-ratio: {feed_ratio}; background: var(--color-bg-tertiary, #fafafa); display: flex; align-items: center; justify-content: center; color: var(--color-text-muted, #999);">Aucune image</div>'}
                <div style="padding: 12px 16px;">
                    {stats_html}
                    <div style="font-size: 14px; line-height: 1.5; white-space: pre-wrap; margin-top: 8px;">{full_caption}</div>
                </div>
                <div style="padding: 8px 16px; border-top: 1px solid var(--color-border-light, #efefef); display: flex; gap: 16px; color: var(--color-text-muted, #8e8e8e); font-size: 13px;">
                    <span>♥️ 0</span>
                    <span>💬 0</span>
                    <span>📤 0</span>
                </div>
            </div>
            """
        else:
            # Fallback reel/other
            html = f"""
            <div style="max-width: 480px; background: var(--color-bg-primary, #fff); color: var(--color-text-primary, #111827); border-radius: 8px; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
                {f'<img src="{photo_url}" style="width: 100%;">' if photo_url else ''}
                <div style="padding: 12px 16px; white-space: pre-wrap;">{full_caption}</div>
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
        # Le parcours Garmin rapide récupère la publication sans charger la
        # relation calendrier. Charger ici l'entrée permet de retrouver
        # l'activité Garmin source au moment du rendu des stats et du visuel.
        if entry is None and pub.calendar_entry_id:
            entry = await self.db.get(EditorialCalendarEntry, pub.calendar_entry_id)
        if entry and getattr(entry, "source_activity_id", None):
            return await self.db.get(SportActivity, entry.source_activity_id)
        return None

    async def get_editorial_brief(self, publication_id: int) -> dict[str, Any]:
        """Retourne le brief V2 sans déclencher de génération ni de publication."""
        from app.services.sport_editorial_engine import build_editorial_brief

        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")
        activity = await self._get_activity_for_publication(pub)
        if activity is None:
            raise ValueError("Activité Garmin introuvable pour cette publication")
        design = pub.design if isinstance(pub.design, dict) else {}
        photos = design.get("carousel") if isinstance(design.get("carousel"), list) else []
        previous = (
            await self.db.execute(
                select(SportPublication)
                .where(SportPublication.athlete_id == pub.athlete_id, SportPublication.id != pub.id)
                .order_by(SportPublication.created_at.desc()).limit(12)
            )
        ).scalars().all()
        return build_editorial_brief(activity, len(photos) or (1 if pub.photo_id else 0), previous)

    async def _ensure_sport_defaults(self, pub: SportPublication, persist_overlay: bool = True) -> SportPublication:
        """Pour les publications sportives : overlay stats sur la photo + choix audio (intelligent/aléatoire)."""
        if not _is_sport_publication(pub):
            return pub

        activity = await self._get_activity_for_publication(pub)
        stats = _sport_stats_from_activity(activity)

        # Les publications Garmin suivent une règle éditoriale déterministe :
        # le titre Garmin, puis uniquement le lieu connu et #trailrunning.
        if activity is not None:
            caption_title, caption_hashtags = _garmin_caption(activity, pub.title)
            pub.title = caption_title
            # Le contenu IA ou sa version éditée par l'utilisateur doit rester
            # disponible pour Instagram et Facebook. Ne pas écraser les hashtags existants.
            if not pub.hashtags:
                pub.hashtags = _ensure_garmin_hashtag(caption_hashtags)

        # Injection des elements graphiques sport_stats (distance / denivele / duree) depuis l'activite Garmin
        design0 = pub.design if isinstance(pub.design, dict) else {}
        design = dict(design0)
        if activity is not None:
            from app.services.sport_editorial_engine import build_editorial_brief
            carousel = design.get("carousel") if isinstance(design.get("carousel"), list) else []
            brief = build_editorial_brief(
                activity,
                len(carousel) or (1 if pub.photo_id else 0),
            )
            # Le style choisi manuellement reste prioritaire.
            existing_engine = design.get("editorial_engine") if isinstance(design.get("editorial_engine"), dict) else {}
            if existing_engine.get("style"):
                brief["style"] = existing_engine["style"]
                brief["direction"]["primary"] = brief["style"]
            design["editorial_engine"] = brief
        new_stats = _sport_stats_elements_to_add(design, activity)
        if new_stats:
            design["elements"] = [
                element for element in (design.get("elements") or [])
                if not (isinstance(element, dict) and element.get("type") == "sport_stats")
            ] + new_stats
        if activity is not None:
            pub.design = design

        # Overlay stats sur la photo (durée, dénivelé, km) - appliqué systématiquement
        if pub.photo_id and stats:
            try:
                from app.services.photo.service import PhotoService
                photo_service = PhotoService(self.db, self.current_user)
                photo = await photo_service._get_owned(pub.photo_id, include_deleted=True)
                storage = photo_service.storage
                src_path = storage.backend_for_photo(photo).original_path(photo.storage_path)
                if persist_overlay and src_path and Path(src_path).is_file():
                    # Éviter de ré-appliquer si déjà un overlay sport généré pour cette photo/stats
                    design = pub.design if isinstance(pub.design, dict) else {}
                    sport_meta = design.get("sport_overlay") or {}
                    signature = f"{pub.photo_id}:{stats.get('duree')}:{stats.get('denivele')}:{stats.get('distance')}:{pub.title or ''}"
                    if sport_meta.get("signature") != signature or not sport_meta.get("overlay_photo_id"):
                        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                            tmp_path = tmp.name
                        out = render_sport_overlay_image(
                            str(src_path), stats, tmp_path, pub.title,
                            (design.get("editorial_engine") or {}).get("style"),
                        )
                        if out:
                            try:
                                data = Path(out).read_bytes()
                                from app.core.config import get_settings
                                settings = get_settings()
                                # réutiliser la logique d'import simple (PhotoService ne permet pas d'injecter des bytes facilement)
                                from app.services.photo.service import sniff_image_format_maybe
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

        # Analyse locale de l'extrait, distincte de la référence Meta ig_audio.
        try:
            from app.services.community_manager.audio_matching import recommend_track
            style = str((pub.design or {}).get("editorial_engine", {}).get("style") or "performance")
            current = (pub.design or {}).get("audio") or {}
            if current.get("track_id") and not current.get("audio_match"):
                recommendation = recommend_track(style, 12.0)
                if recommendation and recommendation.get("track_id") == current.get("track_id"):
                    design = dict(pub.design or {})
                    design["audio"] = {**current, "audio_match": recommendation["excerpt"]}
                    pub.design = design
        except Exception:
            logger.exception("[CM-STUDIO] Impossible d'analyser l'extrait audio sport pour publication %s", pub.id)

        await self.db.flush()
        return pub

    async def ensure_companion_video_job(self, pub: SportPublication, force: bool = False) -> Any:
        """Planifie (idempotent, async) le rendu vidéo musical compagnon d'une publication sportive.

        Conditions : publication sportive, photo présente, audio activé avec piste.
        Ne bloque pas ; le traitement est effectué par le worker photo_jobs (studio_render).
        """
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
        ig_audio = design.get("ig_audio") if isinstance(design.get("ig_audio"), dict) else {}
        track_id = audio_cfg.get("track_id") or audio_cfg.get("track")
        # Une sélection Meta suffit pour générer la vidéo compagnon : son audio
        # sera attaché par Instagram, jamais téléchargé ni transmis à FFmpeg.
        if not audio_cfg.get("enabled", True) and not ig_audio.get("audio_id"):
            return None
        if not ig_audio.get("audio_id") and (not track_id or resolve_track_path(str(track_id)) is None):
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
        design = {**design, "audio": {**audio_cfg, "embedded": False, "audio_status": "meta_attached" if ig_audio.get("audio_id") else "selected"}}
        pub.design = design

        # Déclenchement immédiat best-effort en contexte HTTP (sinon boucle lifespan)
        # Le Quick Reel doit démarrer même si la boucle générale des jobs
        # photo est désactivée dans la configuration.
        try:
            import asyncio

            loop = asyncio.get_running_loop()
            loop.create_task(run_pending_jobs_now())
        except Exception:
            pass

        return job

    @staticmethod
    def _ig_audio_configuration(pub: SportPublication) -> Optional[dict]:
        """Paramètre audio_configuration (Audio API Instagram) pour un Reel.

        Construit depuis design["ig_audio"] (choisi au choix de la photo).
        video_volume=1 : la musique Instagram remplace quasi totalement la
        piste CC0 embarquée dans la vidéo compagnon (minimum Meta = 1).
        """
        design = pub.design if isinstance(pub.design, dict) else {}
        ig_audio = design.get("ig_audio") if isinstance(design, dict) else None
        if not isinstance(ig_audio, dict) or not ig_audio.get("audio_id"):
            return None
        return {
            "audio_id": str(ig_audio["audio_id"]),
            "audio_volume": 100,
            "video_volume": 1,
        }

    async def _ensure_companion_video_photo(self, pub: SportPublication) -> int:
        """Retourne l'ID Photo du MP4 compagnon (vidéo Reel), en attendant son rendu.

        - Video prête + fichier présent -> (re)importe le MP4 comme média Photo
          et retourne son ID.
        - En attente -> déclenche le job et réessaie (max COMPANION_READY_WAIT_SECONDS).
        - Échec -> lève une erreur lisible avec l'erreur de rendu.
        """
        from app.services.photo.jobs import run_pending_jobs_now

        deadline = asyncio.get_running_loop().time() + self.COMPANION_READY_WAIT_SECONDS
        while True:
            design = pub.design if isinstance(pub.design, dict) else {}
            if pub.companion_video_status == "ready" and pub.companion_video_path:
                video_path = Path(pub.companion_video_path)
                if video_path.is_file():
                    media = design.get("companion_video_media") if isinstance(design.get("companion_video_media"), dict) else None
                    if media and media.get("path") == str(video_path) and media.get("photo_id"):
                        photo = await self.db.get(Photo, int(media["photo_id"]))
                        if photo is not None and not photo.is_deleted and photo.mime_type == "video/mp4":
                            return photo.id
                    return await self._import_companion_video(pub, video_path)
                # Fichier perdu : forcer un nouveau rendu
                pub.companion_video_status = "none"
                pub.companion_video_path = None
                await self.db.commit()
            if pub.companion_video_status == "failed":
                raise ValueError(
                    f"La vidéo Reel n'a pas pu être générée : {pub.companion_video_error or 'erreur inconnue'}"
                )
            if pub.companion_video_status not in ("pending", "running"):
                await self.ensure_companion_video_job(pub, force=False)
                await self.db.commit()
            try:
                await run_pending_jobs_now()
            except Exception:
                logger.exception("[CM-STUDIO] Impossible d'exécuter le job de la vidéo compagnon")
            if asyncio.get_running_loop().time() >= deadline:
                raise ValueError(
                    "La vidéo Reel n'est pas encore prête. Veuillez réessayer dans un instant."
                )
            await asyncio.sleep(1)
            await self.db.refresh(pub)

    async def _import_companion_video(self, pub: SportPublication, video_path: Path) -> int:
        """Importe le MP4 compagnon comme média photo (URL signée meta_token)."""
        from uuid import uuid4

        from app.services.photo.storage import get_photo_storage

        data = video_path.read_bytes()
        photo_storage = get_photo_storage()
        backend = photo_storage.backend()
        rel = photo_storage.save_original(
            self.current_user.id, uuid4().hex, ".mp4", data, backend.name
        )
        video_photo = Photo(
            owner_id=self.current_user.id,
            title=f"Reel #{pub.id}",
            original_filename=f"companion_{pub.id}.mp4",
            storage_path=rel,
            storage_backend=backend.name,
            mime_type="video/mp4",
            byte_size=len(data),
            taken_at=datetime.now(timezone.utc),
            content_hash=photo_storage.hash_bytes(data),
            status="ready",
            analysis_status="pending",
        )
        self.db.add(video_photo)
        await self.db.flush()
        design = dict(pub.design) if isinstance(pub.design, dict) else {}
        design["companion_video_media"] = {"path": str(video_path), "photo_id": video_photo.id}
        pub.design = design
        await self.db.commit()
        return video_photo.id

    async def _cleanup_companion_video_media(self, pub: SportPublication) -> None:
        """Supprime le média technique temporaire créé pour l'URL Meta."""
        from app.services.photo.service import PhotoService

        design = pub.design if isinstance(pub.design, dict) else {}
        media = design.get("companion_video_media") if isinstance(design.get("companion_video_media"), dict) else None
        photo_id = media.get("photo_id") if media else None
        if not photo_id:
            return
        photo = await self.db.get(Photo, int(photo_id))
        if photo is not None:
            try:
                storage = PhotoService(self.db, self.current_user).storage
                path = storage.backend_for_photo(photo).original_path(photo.storage_path)
                if path and Path(path).is_file():
                    Path(path).unlink()
            except Exception:
                logger.warning("[CM-STUDIO] Nettoyage du média compagnon impossible: %s", photo_id, exc_info=True)
            await self.db.delete(photo)
        design = dict(design)
        design.pop("companion_video_media", None)
        pub.design = design

    async def _publish_media_photo_id(self, pub: SportPublication) -> int:
        """Source du média de publication : vidéo compagnon Reel (Garmin) ou photo.

        Les publications sportives (Garmin) sont systématiquement publiées
        en Reel (vidéo compagnon + musique IG choisie par IA).
        """
        if not _is_sport_publication(pub):
            return pub.photo_id
        if pub.visual_type != "reel":
            pub.visual_type = "reel"
        await self.db.commit()
        return await self._ensure_companion_video_photo(pub)

    async def publish_to_instagram(
        self, publication_id: int, data: Any
    ) -> SportPublication:
        """Publie une publication validée sur Instagram via l'API Meta."""
        from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
        from app.services.sport_media_publish import MediaPublishService

        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")
        self.assert_publishable_format(pub)
        # Charger le contexte calendrier pour détecter les publications sportives
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        # Publications sportives : overlay stats (durée, dénivelé, km) + audio choisi
        # automatiquement — sans créer de Photo dans le module photo.
        pub = await self._ensure_sport_defaults(pub, persist_overlay=False)

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

        if not (pub.content or "").strip() and not (_is_sport_publication(pub) and (pub.title or pub.hashtags)):
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
            media_photo_id = await self._publish_media_photo_id(pub)
            is_video = pub.visual_type in ("reel", "video")

            if media_photo_id:
                media_info = await media_publish_service.prepare_media_for_publish(
                    media_photo_id, self.current_user.id, size="original"
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
                audio_configuration = self._ig_audio_configuration(pub) if is_reel else None
                if pub.visual_type == "reel" or is_video:
                    instagram_media_id = await meta_service.publish_video(
                        connection, media_url, caption,
                        mime_type=media_info.mime_type if media_info else None,
                        is_reel=is_reel,
                        publication_id=publication_id,
                        audio_configuration=audio_configuration,
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

                # Le MP4 importé comme Photo n'est qu'un support technique pour
                # l'URL Meta : il ne doit pas rester dans le module Photos.
                await self._cleanup_companion_video_media(pub)

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
                await self._cleanup_companion_video_media(pub)
                await self.db.commit()
                await self.db.refresh(pub)

                logger.error(f"Erreur publication Instagram: {e}")
                raise ValueError(f"Échec de la publication Instagram: {str(e)}")

        except MetaPublishError as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = f"Meta API: {str(e)}"
            await self._cleanup_companion_video_media(pub)
            await self.db.commit()
            await self.db.refresh(pub)
            raise ValueError(f"Erreur Meta: {str(e)}")
        except Exception as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = str(e)
            await self._cleanup_companion_video_media(pub)
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
        self.assert_publishable_format(pub)
        # Charger le contexte calendrier pour détecter les publications sportives
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        # Publications sportives : overlay stats (durée, dénivelé, km) + audio choisi
        # automatiquement — sans créer de Photo dans le module photo.
        pub = await self._ensure_sport_defaults(pub, persist_overlay=False)

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

        if not (pub.content or "").strip() and not (_is_sport_publication(pub) and (pub.title or pub.hashtags)):
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
            media_photo_id = await self._publish_media_photo_id(pub)
            is_video = pub.visual_type in ("reel", "video")

            if media_photo_id:
                media_info = await media_publish_service.prepare_media_for_publish(
                    media_photo_id, self.current_user.id, size="original"
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

                # Le MP4 importé comme Photo n'est qu'un support technique pour
                # l'URL Meta : il ne doit pas rester dans le module Photos.
                await self._cleanup_companion_video_media(pub)
                await self.db.commit()
                await self.db.refresh(pub)

                logger.info(f"Publication Facebook Page réussie: media_id={facebook_media_id}, publication_id={publication_id}")
                return pub

            except Exception as e:
                pub.status = "failed"
                pub.failed_at = datetime.now(timezone.utc)
                pub.error_message = str(e)
                await self._cleanup_companion_video_media(pub)
                await self.db.commit()
                await self.db.refresh(pub)
                logger.error(f"Erreur publication Facebook Page: {e}")
                raise ValueError(f"Échec de la publication Facebook Page: {str(e)}")

        except MetaPublishError as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = f"Meta API: {str(e)}"
            await self._cleanup_companion_video_media(pub)
            await self.db.commit()
            await self.db.refresh(pub)
            raise ValueError(f"Erreur Meta: {str(e)}")
        except Exception as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = str(e)
            await self._cleanup_companion_video_media(pub)
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
        self.assert_publishable_format(pub)
        # Charger le contexte calendrier
        if pub.calendar_entry_id:
            entry_result = await self.db.execute(
                select(EditorialCalendarEntry).where(
                    EditorialCalendarEntry.id == pub.calendar_entry_id
                )
            )
            pub.calendar_entry = entry_result.scalar_one_or_none()
        pub = await self._ensure_sport_defaults(pub, persist_overlay=False)

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

        if not (pub.content or "").strip() and not (_is_sport_publication(pub) and (pub.title or pub.hashtags)):
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
            media_photo_id = await self._publish_media_photo_id(pub)
            is_video = pub.visual_type in ("reel", "video")

            if media_photo_id:
                media_service = MediaPublishService(self.db)
                media_infos["instagram"] = await media_service.prepare_media_for_publish(
                    media_photo_id, self.current_user.id, size="original"
                )
                media_infos["facebook"] = await media_service.prepare_media_for_publish(
                    media_photo_id, self.current_user.id, size="original"
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
                            audio_configuration=self._ig_audio_configuration(pub) if is_reel else None,
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
                # Le MP4 importé comme Photo n'est qu'un support technique pour
                # l'URL Meta : il ne doit pas rester dans le module Photos.
                await self._cleanup_companion_video_media(pub)
                await self.db.commit()
                await self.db.refresh(pub)
                logger.info(f"Publication multi-plateforme: IG={ig_success}, FB={fb_success}")
                return pub

            except Exception as e:
                pub.status = "failed"
                pub.failed_at = datetime.now(timezone.utc)
                pub.error_message = str(e)
                await self._cleanup_companion_video_media(pub)
                await self.db.commit()
                await self.db.refresh(pub)
                logger.error(f"Erreur publication multi-plateforme: {e}")
                raise ValueError(f"Échec de la publication: {str(e)}")

        except MetaPublishError as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = f"Meta API: {str(e)}"
            await self._cleanup_companion_video_media(pub)
            await self.db.commit()
            await self.db.refresh(pub)
            raise ValueError(f"Erreur Meta: {str(e)}")
        except Exception as e:
            pub.status = "failed"
            pub.failed_at = datetime.now(timezone.utc)
            pub.error_message = str(e)
            await self._cleanup_companion_video_media(pub)
            await self.db.commit()
            await self.db.refresh(pub)
            logger.exception(f"Erreur publication multi-plateforme: {e}")
            raise ValueError(f"Erreur de publication: {str(e)}")

    async def get_suggested_photos(self, publication_id: int, limit: int = 15) -> list[dict[str, Any]]:
        """Récupère des photos suggérées pour la publication en reliant activités Garmin et dates."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")

        target_date = None
        if pub.calendar_entry_id:
            entry_res = await self.db.execute(
                select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == pub.calendar_entry_id)
            )
            entry = entry_res.scalar_one_or_none()
            if entry and entry.date:
                target_date = entry.date

        return await self._get_suggested_photos_for_date(target_date, limit=limit, current_photo_id=pub.photo_id)

    async def get_suggested_photos_for_activity(self, activity_id: int, limit: int = 15) -> list[dict[str, Any]]:
        """Récupère des photos suggérées pour une activité Garmin (targeting par activity_id).

        Lot 0 (A03) : le parcours Garmin (calendrier, MediaPicker) doit pouvoir
        demander des suggestions réellement liées à une activité et non plus un
        identifiant de publication absent.
        """
        activity_res = await self.db.execute(
            select(SportActivity).where(
                SportActivity.id == activity_id,
                SportActivity.athlete_id == (await self._get_athlete_and_strategy())[0].id,
            )
        )
        activity = activity_res.scalar_one_or_none()
        if not activity:
            raise ValueError("Activité Garmin introuvable")

        target_date = activity.started_at.date() if activity.started_at else None
        return await self._get_suggested_photos_for_date(target_date, limit=limit)

    async def _get_suggested_photos_for_date(
        self, target_date: Optional[Any], limit: int = 15, current_photo_id: Optional[int] = None
    ) -> list[dict[str, Any]]:
        """Photos du user récentes mises en avant pour une date cible (jour éditorial / activité)."""
        athlete, _strategy = await self._get_athlete_and_strategy()

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
                "is_current": (current_photo_id == photo.id),
            })
            if len(results) >= limit:
                break

        return results
