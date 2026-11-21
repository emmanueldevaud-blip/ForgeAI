"""Story Orchestrator — Coordination centrale du Story Studio.

Responsabilités :
- Récupérer les photos sélectionnées et données Garmin
- Organiser les photos en séquences cohérentes
- Déterminer le nombre de Stories optimal
- Générer les compositions via StoryAIComposer
- Préparer les documents de conception Studio v2
- Préparer les rendus FFmpeg
- Gérer le cycle de vie du brouillon (statuts)
"""

import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.photo import Photo
from app.models.sport import (
    EditorialCalendarEntry,
    SportActivity,
    SportAthlete,
    SportPublication,
    StoryDraft,
)
from app.models.user import User
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.community_manager.audio import ensure_audio_config, list_tracks, select_track
from app.services.community_manager.audio_matching import recommend_track
from app.services.community_manager.ig_music import pick_audio_for_photos_bounded
from app.services.community_manager.studio import (
    CommunityManagerStudioService,
    _is_sport_publication,
    _sport_stats_from_activity,
)
from app.services.sport_editorial_engine import build_editorial_brief
from app.services.sport_publications import SportPublicationService

logger = logging.getLogger(__name__)

STORY_FORMAT = {"width": 1080, "height": 1920, "type": "story_916", "platform": "instagram"}

STORY_SLIDE_TYPES = [
    "intro",
    "photo",
    "stats",
    "map",
    "outro",
]

DEFAULT_SLIDE_DURATION = 5.0
MAX_STORIES_PER_DRAFT = 10


class StoryOrchestrator:
    """Service central de coordination pour la création de Stories."""

    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.pub_service = SportPublicationService(db, current_user)
        self.cm_studio = CommunityManagerStudioService(db, current_user)

    async def _get_athlete(self) -> SportAthlete:
        return await self.pub_service.get_or_create_athlete()

    # ------------------------------------------------------------------ #
    # Création du brouillon depuis activité Garmin + photos sélectionnées
    # ------------------------------------------------------------------ #
    async def create_draft_from_garmin(
        self,
        activity_id: int,
        selected_photo_ids: list[int],
        calendar_entry_id: int | None = None,
    ) -> StoryDraft:
        """Crée un StoryDraft à partir d'une activité Garmin et d'une sélection de photos."""
        athlete = await self._get_athlete()

        # Vérifier l'activité
        activity_result = await self.db.execute(
            select(SportActivity).where(
                SportActivity.id == activity_id,
                SportActivity.athlete_id == athlete.id,
            )
        )
        activity = activity_result.scalar_one_or_none()
        if not activity:
            raise ValueError("Activité Garmin introuvable")

        # Vérifier les photos (accessibles par l'utilisateur)
        photos = await self._validate_photos(selected_photo_ids)
        if not photos:
            raise ValueError("Aucune photo valide sélectionnée")

        # Créer le brouillon
        draft = StoryDraft(
            athlete_id=athlete.id,
            source="garmin",
            source_activity_id=activity_id,
            calendar_entry_id=calendar_entry_id,
            selected_asset_ids=[p.id for p in photos],
            status="preparing",
        )
        self.db.add(draft)
        await self.db.flush()

        # Lancer la préparation asynchrone (non bloquant)
        # Pour l'instant on prépare synchroniquement pour simplicité
        await self._prepare_draft(draft, activity, photos)

        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def _validate_photos(self, photo_ids: list[int]) -> list[Photo]:
        """Filtre et valide les photos sélectionnées."""
        if not photo_ids:
            return []
        result = await self.db.execute(
            select(Photo).where(
                Photo.id.in_(photo_ids),
                Photo.is_deleted == False,  # noqa: E712
                Photo.owner_id == self.current_user.id,
            )
        )
        photos = list(result.scalars().all())
        # Maintenir l'ordre de sélection
        photo_map = {p.id: p for p in photos}
        return [photo_map[pid] for pid in photo_ids if pid in photo_map]

    # ------------------------------------------------------------------ #
    # Préparation automatique complète (Orchestrateur)
    # ------------------------------------------------------------------ #
    async def _prepare_draft(
        self,
        draft: StoryDraft,
        activity: SportActivity,
        photos: list[Photo],
    ) -> None:
        """Prépare automatiquement le brouillon : slides, design, audio, textes."""
        try:
            draft.status = "preparing"
            await self.db.flush()

            # 1. Organiser les photos en séquences logiques
            slide_groups = self._organize_photos_into_slides(photos, activity)

            # 2. Générer les compositions via IA Composer
            composer = StoryAIComposer(self.db, self.current_user)
            slides_data = await composer.compose_slides(activity, photos, slide_groups)

            # 3. Construire les documents de conception Studio v2 par slide
            design_documents = []
            for i, slide in enumerate(slides_data):
                design = self._build_design_document(slide, activity, photos, i)
                design_documents.append(design)

            # 4. Préparer la configuration audio globale
            audio_config = await self._prepare_audio_config(activity, photos, slides_data)

            # 5. Générer hashtags et légende commune
            hashtags = self._generate_hashtags(activity)
            caption = self._generate_caption(activity, slides_data)

            # 6. Mettre à jour le brouillon
            draft.slides = slides_data
            draft.design_documents = design_documents
            draft.audio_configuration = audio_config
            draft.hashtags = hashtags
            draft.caption = caption
            draft.status = "ready"
            draft.prepared_at = datetime.now(timezone.utc)

            await self.db.flush()
            logger.info(f"StoryDraft {draft.id} préparé : {len(slides_data)} slides")

        except Exception as exc:
            logger.exception(f"Erreur préparation StoryDraft {draft.id}")
            draft.status = "failed"
            draft.error_message = str(exc)
            await self.db.flush()
            raise

    def _organize_photos_into_slides(
        self, photos: list[Photo], activity: SportActivity
    ) -> list[dict]:
        """Organise les photos en groupes logiques pour créer les slides."""
        n = len(photos)
        if n == 0:
            return []

        groups = []

        # Slide d'intro (toujours la première photo)
        groups.append({
            "type": "intro",
            "photo_indices": [0],
            "focus": "hook",
        })

        # Slides photos principales
        remaining = list(range(1, n))
        if remaining:
            # Grouper par 1-2 photos selon le nombre total
            if n <= 3:
                # Une slide par photo restante
                for idx in remaining:
                    groups.append({
                        "type": "photo",
                        "photo_indices": [idx],
                        "focus": "moment",
                    })
            elif n <= 6:
                # Paires de photos
                for i in range(0, len(remaining), 2):
                    pair = remaining[i:i+2]
                    groups.append({
                        "type": "photo",
                        "photo_indices": pair,
                        "focus": "sequence",
                    })
            else:
                # 3 groupes : début, milieu, fin
                third = max(1, len(remaining) // 3)
                groups.append({
                    "type": "photo",
                    "photo_indices": remaining[:third],
                    "focus": "start",
                })
                groups.append({
                    "type": "photo",
                    "photo_indices": remaining[third:2*third],
                    "focus": "middle",
                })
                groups.append({
                    "type": "photo",
                    "photo_indices": remaining[2*third:],
                    "focus": "end",
                })

        # Slide de stats (toujours incluse si données Garmin)
        if activity.distance_m or activity.elevation_gain_m or activity.duration_seconds:
            groups.append({
                "type": "stats",
                "photo_indices": [],  # Utilise un fond ou la dernière photo
                "focus": "stats",
            })

        # Slide de conclusion
        groups.append({
            "type": "outro",
            "photo_indices": [n-1] if n > 0 else [],
            "focus": "closing",
        })

        # Limiter le nombre de Stories
        return groups[:MAX_STORIES_PER_DRAFT]

    def _build_design_document(
        self,
        slide: dict,
        activity: SportActivity,
        photos: list[Photo],
        index: int,
    ) -> dict:
        """Construit un document de conception Studio v2 pour une slide."""
        photo_indices = slide.get("photo_indices", [])
        slide_photos = [photos[i] for i in photo_indices if i < len(photos)]

        # Format 9:16 pour Stories
        design = {
            "version": 2,
            "format": STORY_FORMAT,
            "background": {"color": "#000000"},
            "elements": [],
            "carousel": [p.id for p in slide_photos] if slide_photos else [],
            "timeline": {
                "fps": 30,
                "tracks": [],
            },
        }

        # Ajouter l'image de fond (première photo du groupe ou photo par défaut)
        if slide_photos:
            main_photo = slide_photos[0]
            design["background"] = {
                "type": "photo",
                "photo_id": main_photo.id,
                "crop": {"x": 0, "y": 0, "w": 1, "h": 1},
            }
            design["carousel"] = [p.id for p in slide_photos]

        # Éléments selon le type de slide
        if slide["type"] == "intro":
            design["elements"].extend(self._build_intro_elements(activity, slide))
        elif slide["type"] == "photo":
            design["elements"].extend(self._build_photo_elements(slide, activity))
        elif slide["type"] == "stats":
            design["elements"].extend(self._build_stats_elements(activity, slide_photos))
        elif slide["type"] == "map":
            design["elements"].extend(self._build_map_elements(activity))
        elif slide["type"] == "outro":
            design["elements"].extend(self._build_outro_elements(activity, slide))

        return design

    def _build_intro_elements(self, activity: SportActivity, slide: dict) -> list[dict]:
        """Éléments pour la slide d'intro (accroche)."""
        w, h = STORY_FORMAT["width"], STORY_FORMAT["height"]
        elements = []

        # Titre principal (accroche)
        hook = slide.get("hook") or self._generate_hook(activity)
        elements.append({
            "id": f"el-hook-{activity.id}",
            "type": "text",
            "text": hook,
            "x": w / 2,
            "y": h * 0.35,
            "w": w * 0.9,
            "h": h * 0.25,
            "size": max(48, int(w * 0.06)),
            "font": "Arial",
            "color": "#ffffff",
            "bold": True,
            "italic": False,
            "align": "center",
            "shadow": True,
            "opacity": 1,
            "rotation": 0,
        })

        # Sous-titre (date + lieu)
        date_str = activity.started_at.strftime("%d %B %Y") if activity.started_at else ""
        location = self._get_location_hashtag(activity)
        subtitle = f"{date_str} {location}".strip()
        if subtitle:
            elements.append({
                "id": f"el-subtitle-{activity.id}",
                "type": "text",
                "text": subtitle,
                "x": w / 2,
                "y": h * 0.55,
                "w": w * 0.8,
                "h": 60,
                "size": max(24, int(w * 0.03)),
                "font": "Arial",
                "color": "#cccccc",
                "bold": False,
                "italic": False,
                "align": "center",
                "shadow": True,
                "opacity": 0.9,
            })

        return elements

    def _build_photo_elements(self, slide: dict, activity: SportActivity) -> list[dict]:
        """Éléments pour une slide photo (légende contextuelle)."""
        w, h = STORY_FORMAT["width"], STORY_FORMAT["height"]
        elements = []

        # Texte contextuel en bas
        caption = slide.get("caption") or self._generate_photo_caption(activity, slide.get("focus"))
        if caption:
            elements.append({
                "id": f"el-caption-{slide.get('focus')}-{activity.id}",
                "type": "text",
                "text": caption,
                "x": w / 2,
                "y": h * 0.85,
                "w": w * 0.9,
                "h": 80,
                "size": max(28, int(w * 0.035)),
                "font": "Arial",
                "color": "#ffffff",
                "bold": False,
                "italic": False,
                "align": "center",
                "shadow": True,
                "opacity": 0.95,
            })

        return elements

    def _build_stats_elements(
        self, activity: SportActivity, photos: list[Photo]
    ) -> list[dict]:
        """Éléments pour la slide de stats (distance, D+, durée)."""
        w, h = STORY_FORMAT["width"], STORY_FORMAT["height"]
        elements = []
        stats = _sport_stats_from_activity(activity)

        # Titre "STATS"
        elements.append({
            "id": f"el-stats-title-{activity.id}",
            "type": "text",
            "text": "STATISTIQUES",
            "x": w / 2,
            "y": h * 0.2,
            "w": w * 0.8,
            "h": 60,
            "size": max(28, int(w * 0.035)),
            "font": "Arial",
            "color": "#ffffff",
            "bold": True,
            "italic": False,
            "align": "center",
            "shadow": True,
            "opacity": 1,
        })

        # Stats en grille
        stat_items = []
        if stats.get("distance"):
            stat_items.append(("DISTANCE", stats["distance"]))
        if stats.get("duree"):
            stat_items.append(("TEMPS", stats["duree"]))
        if stats.get("denivele"):
            stat_items.append(("DÉNIVELÉ", stats["denivele"]))

        start_y = h * 0.35
        for i, (label, value) in enumerate(stat_items):
            elements.append({
                "id": f"el-stat-{label.lower()}-{activity.id}",
                "type": "sport_stats",
                "stat": label.lower(),
                "label": label,
                "value": value.split()[0],
                "unit": " ".join(value.split()[1:]) if len(value.split()) > 1 else "",
                "x": w / 2,
                "y": start_y + i * 120,
                "w": w * 0.7,
                "h": 100,
                "size": max(42, int(w * 0.055)),
                "font": "Arial",
                "color": "#ffffff",
                "bold": True,
                "italic": False,
                "shadow": True,
                "align": "center",
                "opacity": 1,
            })

        return elements

    def _build_map_elements(self, activity: SportActivity) -> list[dict]:
        """Éléments pour la slide de carte (placeholder - à développer)."""
        # TODO: Importer la trace GPS et générer une image de carte
        return []

    def _build_outro_elements(self, activity: SportActivity, slide: dict) -> list[dict]:
        """Éléments pour la slide de conclusion."""
        w, h = STORY_FORMAT["width"], STORY_FORMAT["height"]
        elements = []

        # Signature / CTA
        cta = slide.get("cta") or "Suivez l'aventure ! 🏃‍♂️"
        elements.append({
            "id": f"el-cta-{activity.id}",
            "type": "text",
            "text": cta,
            "x": w / 2,
            "y": h * 0.5,
            "w": w * 0.9,
            "h": 100,
            "size": max(36, int(w * 0.045)),
            "font": "Arial",
            "color": "#ffffff",
            "bold": True,
            "italic": False,
            "align": "center",
            "shadow": True,
            "opacity": 1,
        })

        # Hashtag de marque
        elements.append({
            "id": f"el-brand-{activity.id}",
            "type": "text",
            "text": "#Jepepagtrail",
            "x": w / 2,
            "y": h * 0.75,
            "w": w * 0.8,
            "h": 60,
            "size": max(24, int(w * 0.03)),
            "font": "Arial",
            "color": "#888888",
            "bold": False,
            "italic": False,
            "align": "center",
            "shadow": False,
            "opacity": 0.8,
        })

        return elements

    async def _prepare_audio_config(
        self,
        activity: SportActivity,
        photos: list[Photo],
        slides_data: list[dict],
    ) -> dict:
        """Prépare la configuration audio globale pour le brouillon."""
        # Utiliser le système existant pour choisir une musique
        cover_photo_id = photos[0].id if photos else None

        design = {"format": STORY_FORMAT}
        try:
            # Essayer de choisir via le catalogue Instagram (vision + titre)
            if cover_photo_id:
                ig_audio = await pick_audio_for_photos_bounded(
                    self.db, self.current_user, [cover_photo_id],
                    title=slides_data[0].get("hook") if slides_data else "",
                    hashtags=self._generate_hashtags(activity),
                )
                if ig_audio:
                    return {
                        "source": "instagram",
                        "ig_audio": ig_audio,
                        "local_track": None,
                    }
        except Exception as exc:
            logger.warning(f"Choix musique IG échoué: {exc}")

        # Fallback : piste locale (heuristique + aléatoire)
        local_config = ensure_audio_config(
            design,
            activity=activity,
            tone="performance",
            force=True,
        )
        return {
            "source": "local",
            "ig_audio": None,
            "local_track": local_config.get("audio"),
        }

    def _generate_hashtags(self, activity: SportActivity) -> str:
        """Génère les hashtags pour l'activité."""
        tags = ["#trailrunning", "#trail", "#running"]
        location = self._get_location_hashtag(activity)
        if location:
            tags.append(location)
        # Type de sport
        if activity.sport_type:
            tags.append(f"#{activity.sport_type.lower()}")
        return " ".join(tags)

    def _generate_caption(self, activity: SportActivity, slides_data: list[dict]) -> str:
        """Génère une légende commune pour l'ensemble des Stories."""
        hook = slides_data[0].get("hook") if slides_data else self._generate_hook(activity)
        hashtags = self._generate_hashtags(activity)
        return f"{hook}\n\n{hashtags}"

    def _generate_hook(self, activity: SportActivity) -> str:
        """Génère une accroche courte et percutante."""
        distance_km = (activity.distance_m or 0) / 1000
        elev = int(activity.elevation_gain_m or 0)

        hooks = [
            f"{distance_km:.1f} km pour rien. Juste le plaisir. 🏃‍♂️",
            f"D+{elev}m. Les cuisses s'en souviennent encore. ⛰️",
            f"Une sortie de {distance_km:.1f}km. Garmin a validé. Moi aussi. ✅",
            f"Quand le D+ fait mal mais que le sourire reste. 😅",
            f"{distance_km:.1f}km, {elev}m D+. Pas mal pour un mardi. 💪",
        ]
        return random.choice(hooks)

    def _generate_photo_caption(self, activity: SportActivity, focus: str) -> str:
        """Génère une légende contextuelle pour une slide photo."""
        captions = {
            "start": "C'est parti ! 🚀",
            "middle": "Au cœur de l'effort 💪",
            "end": "L'arrivée approche 🏁",
            "moment": "Un instant suspendu ✨",
            "sequence": "La rythme s'installe 🎵",
        }
        return captions.get(focus, "Trail running 🏃‍♂️")

    def _get_location_hashtag(self, activity: SportActivity) -> str | None:
        """Extrait le hashtag de lieu depuis les métadonnées Garmin."""
        metadata = getattr(activity, "metadata_json", None) or {}
        summary = metadata.get("garmin_summary") if isinstance(metadata, dict) else None
        if not isinstance(summary, dict):
            summary = metadata if isinstance(metadata, dict) else {}
        for key in ("locationName", "location", "city"):
            value = summary.get(key)
            if isinstance(value, str) and value.strip():
                import re
                slug = re.sub(r"[^\wÀ-ÿ]+", "", value.strip(), flags=re.UNICODE)
                if slug:
                    return f"#{slug}"
        return None

    # ------------------------------------------------------------------ #
    # Gestion du cycle de vie du brouillon
    # ------------------------------------------------------------------ #
    async def get_draft(self, draft_id: int) -> Optional[StoryDraft]:
        """Récupère un brouillon avec ses relations."""
        athlete = await self._get_athlete()
        result = await self.db.execute(
            select(StoryDraft)
            .where(StoryDraft.id == draft_id, StoryDraft.athlete_id == athlete.id)
            .options(
                selectinload(StoryDraft.source_activity),
                selectinload(StoryDraft.calendar_entry),
            )
        )
        return result.scalar_one_or_none()

    async def update_draft_status(self, draft_id: int, status: str) -> Optional[StoryDraft]:
        """Met à jour le statut d'un brouillon."""
        draft = await self.get_draft(draft_id)
        if not draft:
            return None
        draft.status = status
        if status == "editing":
            draft.updated_at = datetime.now(timezone.utc)
        elif status == "awaiting_validation":
            draft.validated_at = datetime.now(timezone.utc)
        elif status == "published":
            draft.published_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def add_render_job(self, draft_id: int, slide_index: int, job_id: str) -> Optional[StoryDraft]:
        """Ajoute un job de rendu pour une slide."""
        draft = await self.get_draft(draft_id)
        if not draft:
            return None
        jobs = list(draft.render_jobs or [])
        jobs.append({
            "slide_index": slide_index,
            "job_id": job_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        draft.render_jobs = jobs
        draft.status = "rendering"
        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def update_render_job_status(
        self, draft_id: int, job_id: str, status: str, output_path: str | None = None, error: str | None = None
    ) -> Optional[StoryDraft]:
        """Met à jour le statut d'un job de rendu."""
        draft = await self.get_draft(draft_id)
        if not draft:
            return None
        jobs = list(draft.render_jobs or [])
        for job in jobs:
            if job.get("job_id") == job_id:
                job["status"] = status
                if output_path:
                    job["output_path"] = output_path
                if error:
                    job["error"] = error
                job["updated_at"] = datetime.now(timezone.utc).isoformat()
                break
        draft.render_jobs = jobs
        # Vérifier si tous les jobs sont terminés
        if all(j.get("status") == "done" for j in jobs):
            draft.status = "awaiting_validation"
        elif any(j.get("status") == "failed" for j in jobs):
            draft.status = "failed"
            draft.error_message = error or "Échec du rendu"
        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def add_publication_result(
        self, draft_id: int, slide_index: int, platform: str, media_id: str, permalink: str
    ) -> Optional[StoryDraft]:
        """Ajoute un résultat de publication pour une slide."""
        draft = await self.get_draft(draft_id)
        if not draft:
            return None
        results = list(draft.publication_results or [])
        results.append({
            "slide_index": slide_index,
            "platform": platform,
            "media_id": media_id,
            "permalink": permalink,
            "published_at": datetime.now(timezone.utc).isoformat(),
        })
        draft.publication_results = results
        # Si toutes les slides sont publiées sur au moins une plateforme
        published_slides = set(r["slide_index"] for r in results)
        total_slides = len(draft.slides or [])
        if len(published_slides) >= total_slides:
            draft.status = "published"
            draft.published_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(draft)
        return draft

    async def list_drafts(
        self, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """Liste les brouillons de l'utilisateur."""
        athlete = await self._get_athlete()
        query = select(StoryDraft).where(StoryDraft.athlete_id == athlete.id)
        if status:
            query = query.where(StoryDraft.status == status)
        query = query.order_by(StoryDraft.created_at.desc())
        total = (await self.db.execute(
            select(sa.func.count(StoryDraft.id)).where(StoryDraft.athlete_id == athlete.id)
            if not status else select(sa.func.count(StoryDraft.id)).where(
                StoryDraft.athlete_id == athlete.id, StoryDraft.status == status
            )
        )).scalar() or 0
        query = query.offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(query)).scalars().all()
        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def delete_draft(self, draft_id: int) -> bool:
        """Supprime un brouillon (si pas publié)."""
        draft = await self.get_draft(draft_id)
        if not draft:
            return False
        if draft.status == "published":
            raise ValueError("Impossible de supprimer un brouillon déjà publié")
        await self.db.delete(draft)
        await self.db.commit()
        return True


class StoryAIComposer:
    """Moteur de composition automatique des slides via IA."""

    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    async def compose_slides(
        self,
        activity: SportActivity,
        photos: list[Photo],
        slide_groups: list[dict],
    ) -> list[dict]:
        """Génère les données de composition pour chaque slide via IA."""
        # Récupérer la stratégie éditoriale pour le ton
        from app.models.sport import CommunityManagerStrategy
        result = await self.db.execute(
            select(CommunityManagerStrategy).where(
                CommunityManagerStrategy.athlete_id == activity.athlete_id
            )
        )
        strategy = result.scalar_one_or_none()

        # Construire le prompt pour l'IA
        prompt = self._build_composition_prompt(activity, photos, slide_groups, strategy)

        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=STORY_COMPOSER_SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=2000,
            )
            payload = self._parse_ai_response(response.text)
            return self._merge_with_groups(payload, slide_groups)
        except AIGatewayError as exc:
            logger.warning(f"IA indisponible pour composition: {exc}")
            return self._fallback_composition(activity, photos, slide_groups)

    def _build_composition_prompt(
        self,
        activity: SportActivity,
        photos: list[Photo],
        slide_groups: list[dict],
        strategy: CommunityManagerStrategy | None,
    ) -> str:
        """Construit le prompt pour la composition IA."""
        stats = {
            "distance_km": round((activity.distance_m or 0) / 1000, 1),
            "elevation_m": int(activity.elevation_gain_m or 0),
            "duration": self._format_duration(activity.duration_seconds),
            "sport_type": activity.sport_type,
            "avg_pace": self._format_pace(activity.avg_pace_sec_km),
            "avg_hr": int(activity.avg_heart_rate) if activity.avg_heart_rate else None,
        }

        photo_count = len(photos)
        tone = (strategy.tone or ["humour", "performance"])[0] if strategy else "humour"

        return f"""
Activité Garmin (données réelles uniquement) :
{json.dumps(stats, ensure_ascii=False)}

Photos disponibles : {photo_count} photos sélectionnées par l'utilisateur.
Structure demandée : {len(slide_groups)} slides.

Groupes de slides :
{json.dumps([{"type": g["type"], "focus": g.get("focus"), "photo_count": len(g.get("photo_indices", []))} for g in slide_groups], ensure_ascii=False)}

Ton éditorial : {tone}
{("Identité de marque : " + strategy.brand_identity) if strategy and strategy.brand_identity else ""}

Génère pour CHAQUE slide :
1. hook (accroche courte, max 80 caractères) - UNIQUEMENT pour la slide d'intro
2. caption (texte contextuel court, max 120 caractères) - pour slides photo
3. cta (call-to-action pour l'outro)
4. suggestion de sticker pertinent (distance, dénivelé, allure, FC, carte, météo)
5. style visuel suggéré (cinematique, humour, dynamique, performance)

IMPORTANT :
- N'INVENTE AUCUNE donnée. Utilise uniquement les stats réelles ci-dessus.
- Texte court, naturel, lisible sur mobile (format 9:16).
- Humour et autodérision privilégiés pour le trail.
- Hashtags géographiques et sportifs pertinents.
- Réponds UNIQUEMENT en JSON avec la clé "slides" (liste d'objets).
"""

    def _parse_ai_response(self, text: str) -> dict:
        """Parse la réponse JSON de l'IA."""
        if not text:
            return {}
        cleaned = text.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            if len(parts) >= 3:
                cleaned = parts[1]
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
        try:
            s, e = cleaned.find("{"), cleaned.rfind("}")
            if s >= 0 and e > s:
                return json.loads(cleaned[s:e+1])
        except (json.JSONDecodeError, ValueError):
            pass
        return {}

    def _merge_with_groups(
        self, payload: dict, slide_groups: list[dict]
    ) -> list[dict]:
        """Fusionne la réponse IA avec les groupes de slides."""
        ai_slides = payload.get("slides", []) if isinstance(payload, dict) else []
        merged = []
        for i, group in enumerate(slide_groups):
            ai_data = ai_slides[i] if i < len(ai_slides) else {}
            merged.append({
                **group,
                "hook": ai_data.get("hook"),
                "caption": ai_data.get("caption"),
                "cta": ai_data.get("cta"),
                "sticker_suggestion": ai_data.get("sticker"),
                "visual_style": ai_data.get("visual_style", "performance"),
            })
        return merged

    def _fallback_composition(
        self, activity: SportActivity, photos: list[Photo], slide_groups: list[dict]
    ) -> list[dict]:
        """Composition de repli sans IA."""
        distance_km = round((activity.distance_m or 0) / 1000, 1)
        elev = int(activity.elevation_gain_m or 0)
        hooks = [
            f"{distance_km:.1f} km pour rien. Juste le plaisir. 🏃‍♂️",
            f"D+{elev}m. Les cuisses s'en souviennent encore. ⛰️",
            f"Une sortie de {distance_km:.1f}km. Garmin a validé. Moi aussi. ✅",
        ]
        return [
            {
                **group,
                "hook": random.choice(hooks) if group["type"] == "intro" else None,
                "caption": self._generate_photo_caption(activity, group.get("focus", "")) if group["type"] == "photo" else None,
                "cta": "Suivez l'aventure ! 🏃‍♂️" if group["type"] == "outro" else None,
                "sticker_suggestion": self._suggest_sticker(activity, group["type"]),
                "visual_style": "performance",
            }
            for group in slide_groups
        ]

    def _suggest_sticker(self, activity: SportActivity, slide_type: str) -> str | None:
        """Suggère un sticker pertinent selon le type de slide."""
        if slide_type == "stats":
            return "stats"
        if slide_type == "intro":
            return "location"
        if slide_type == "photo":
            return "music"
        if slide_type == "outro":
            return "hashtag"
        return None

    def _format_duration(self, seconds: int | None) -> str | None:
        if not seconds:
            return None
        h, rem = divmod(int(seconds), 3600)
        m = rem // 60
        return f"{h}h{m:02d}" if h else f"{m} min"

    def _format_pace(self, pace_sec_km: float | None) -> str | None:
        if not pace_sec_km:
            return None
        m = int(pace_sec_km // 60)
        s = int(pace_sec_km % 60)
        return f"{m}:{s:02d}/km"


# Prompt système pour le compositeur IA
STORY_COMPOSER_SYSTEM_PROMPT = """
# RÔLE : EXPERT STORY INSTAGRAM — TRAIL RUNNING & ULTRA-TRAIL

Tu es un expert en création de Stories Instagram pour traileurs et ultra-trailers.
Ton objectif : transformer une activité Garmin + photos en Stories 9:16 prêtes à publier.

## CONTRAINTES ABSOLUES
- JAMAIS inventer de données. Seulement les stats Garmin fournies.
- Format 9:16 vertical mobile. Texte court, gros, lisible.
- 1 slide = 1 Story Instagram (5-7 secondes).
- Max 10 Stories par série.

## TON : HUMOUR & AUTODÉRISION (prioritaire pour le trail)
- "J'avais prévu 15km. Garmin en a décidé 22."
- "Le D+ était gratuit. La souffrance aussi."
- "Mon cardio va bien. Mon ego un peu moins."
- Court, percutant, identifiable.

## STRUCTURE TYPE D'UNE SÉRIE
1. INTRO : Accroche forte (hook) + date/lieu
2. PHOTOS : 1-3 slides "moment" avec légende courte
3. STATS : Distance / Temps / D+ en gros chiffres
4. OUTRO : CTA + hashtag de marque (#Jepepagtrail)

## STICKERS PERTINENTS
- Distance / Allure / FC / D+ / Carte GPS / Météo / Heure / Musique
- Un seul sticker principal par slide.

## SORTIE JSON OBLIGATOIRE
{
  "slides": [
    {"hook": "...", "caption": "...", "cta": "...", "sticker": "stats", "visual_style": "performance"},
    ...
  ]
}
"""