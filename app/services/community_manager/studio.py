"""Service Studio Community Manager V2 - Création intelligente de publications."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.sport import (
    CommunityManagerStrategy,
    EditorialCalendarEntry,
    SportActivity,
    SportAthlete,
    SportPublication,
    SportInstagramConnection,
)
from app.models.user import User
from app.schemas.sport import (
    PublicationDraftUpdate,
    PublicationGenerateFromCalendarRequest,
    PublicationValidateRequest,
    PublicationPreviewRequest,
)
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.sport_publications import SportPublicationService, SYSTEM_PROMPT
from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
from app.services.sport_media_publish import MediaPublishService

logger = logging.getLogger(__name__)


class CommunityManagerStudioService:
    """Service pour le Studio de création V2."""

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

        if entry.status != "planifié":
            raise ValueError("L'entrée doit être validée (statut 'planifié') pour créer une publication")

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
        return pub

    async def update_draft(
        self, publication_id: int, data: PublicationDraftUpdate
    ) -> Optional[SportPublication]:
        """Met à jour un brouillon (texte, hashtags, visuel, ton, propositions)."""
        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            return None

        # Vérifier que l'utilisateur a le droit (déjà fait par get_publication)

        # Mettre à jour les champs fournis
        if data.title is not None:
            pub.title = data.title
        if data.content is not None:
            pub.content = data.content
        if data.hashtags is not None:
            pub.hashtags = data.hashtags
        if data.photo_id is not None:
            pub.photo_id = data.photo_id
        if data.visual_type is not None:
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
                        pub.title = p.get("title")
                        pub.content = p.get("content")
                        pub.hashtags = p.get("hashtags")
        if data.proposals is not None:
            pub.proposals = data.proposals
        if data.styles is not None:
            # Valider les styles
            from app.services.sport_publications import _validate_styles as validate_styles
            pub.styles = validate_styles(data.styles) or pub.styles
        if data.custom_instructions is not None:
            pub.custom_instructions = data.custom_instructions.strip() or None

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
                content = str(p.get("content") or "").strip()
                if not content:
                    continue
                proposals.append({
                    "title": str(p.get("title")).strip() if p.get("title") else None,
                    "content": content,
                    "hashtags": str(p.get("hashtags")).strip() if p.get("hashtags") else None,
                    "format": str(p.get("format")).strip() if p.get("format") else "photo",
                    "idee_visuelle": str(p.get("idee_visuelle")).strip() if p.get("idee_visuelle") else None,
                    "objectif": str(p.get("objectif")).strip() if p.get("objectif") else None,
                })

        if not proposals:
            proposals = [{"title": "Variante", "content": text, "hashtags": None, "format": "photo", "idee_visuelle": None, "objectif": None}]

        return proposals[:count]

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

        # Rendu HTML simple pour prévisualisation
        content = pub.content or ""
        hashtags = pub.hashtags or ""
        title = pub.title or ""
        photo_url = None
        if pub.photo_id:
            photo_url = f"/photos/{pub.photo_id}/file?size=medium"

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
        else:
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
        }

    async def publish_to_instagram(
        self, publication_id: int, data: Any
    ) -> SportPublication:
        """Publie une publication validée sur Instagram via l'API Meta."""
        from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
        from app.services.sport_media_publish import MediaPublishService

        pub = await self.pub_service.get_publication(publication_id)
        if not pub:
            raise ValueError("Publication introuvable")

        if pub.status != "validated":
            raise ValueError("Seules les publications validées peuvent être publiées")

        if not (pub.content or "").strip():
            raise ValueError("Le contenu de la publication est vide")

        # Vérifier qu'il y a un visuel
        if not pub.photo_id and not pub.visual_generation_prompt:
            raise ValueError("Un visuel est requis pour la publication Instagram")

        # Récupérer l'athlète et la connexion Instagram
        athlete, strategy = await self._get_athlete_and_strategy()

        # Récupérer la connexion Instagram
        from app.models.sport import SportInstagramConnection
        conn_result = await self.db.execute(
            select(SportInstagramConnection).where(
                SportInstagramConnection.user_id == self.current_user.id,
                SportInstagramConnection.status == "active",
            )
        )
        connection = conn_result.scalar_one_or_none()
        if not connection:
            raise ValueError("Aucun compte Instagram connecté. Connectez un compte dans les paramètres.")

        if not connection.instagram_business_account_id:
            raise ValueError("Compte Instagram Business non configuré")

        # Marquer comme "en cours de publication"
        pub.status = "publishing"
        await self.db.commit()

        try:
            # Préparer l'URL du média
            media_publish_service = MediaPublishService(self.db)
            media_url = None
            is_video = pub.visual_type in ("reel", "video")

            if pub.photo_id:
                # Préparer l'URL publique du média
                media_service = MediaPublishService(self.db)
                media_url = await media_service.prepare_media_for_publish(pub.photo_id, self.current_user.id)
            elif pub.visual_generation_prompt:
                # TODO: Génération d'image IA - pour l'instant erreur
                raise ValueError("La génération d'images IA n'est pas encore disponible. Sélectionnez une photo.")

            if not media_url:
                raise ValueError("Impossible de préparer le média pour publication")

            # Construire le caption complet
            caption = pub.content or ""
            if pub.hashtags:
                caption += f"\n\n{pub.hashtags}"

            # Publier via Meta
            meta_service = MetaPublishService(self.db)
            connection_result = await self.db.execute(
                select(SportInstagramConnection).where(
                    SportInstagramConnection.user_id == self.current_user.id,
                    SportInstagramConnection.status == "active",
                )
            )
            connection = connection_result.scalar_one_or_none()

            meta_service = MetaPublishService(self.db)

            try:
                if pub.visual_type == "reel" or is_video:
                    instagram_media_id = await meta_service.publish_video(connection, media_url, caption)
                else:
                    instagram_media_id = await meta_service.publish_photo(connection, media_url, caption)

                # Récupérer le permalink
                permalink = await meta_service.get_media_permalink(connection, instagram_media_id)

                # Marquer comme publiée avec succès
                pub.status = "shared"
                pub.shared_at = datetime.now(timezone.utc)
                pub.instagram_media_id = instagram_media_id
                pub.instagram_permalink = permalink
                pub.error_message = None

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