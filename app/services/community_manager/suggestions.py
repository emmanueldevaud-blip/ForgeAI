"""Moteur de suggestions éditoriales hebdomadaires (3 stories/semaine).

Génère des propositions d'entrées de calendrier de type story_souvenir et
story_edito, de faE§on idempotente (une semaine = maximum 3 suggestions actives).

Les suggestions ne sont jamais publiées automatiquement sur Instagram.
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import (
    EditorialCalendarEntry,
    CommunityManagerStrategy,
    SportActivity,
    SportAthlete,
)
from app.models.user import User
from app.services.ai_gateway import AIGatewayError, ai_gateway

logger = logging.getLogger(__name__)

# Jours de publication suggérés (mardi, jeudi, samedi)
_SUGGESTION_WEEKDAYS = [1, 3, 5]  # lundi=0 dans Python


class EditorialSuggestionService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    async def _get_athlete(self) -> SportAthlete | None:
        result = await self.db.execute(
            select(SportAthlete).where(SportAthlete.user_id == self.current_user.id)
        )
        return result.scalar_one_or_none()

    async def _get_strategy(self) -> CommunityManagerStrategy | None:
        athlete = await self._get_athlete()
        if not athlete:
            return None
        result = await self.db.execute(
            select(CommunityManagerStrategy).where(
                CommunityManagerStrategy.athlete_id == athlete.id
            )
        )
        return result.scalar_one_or_none()

    def _iso_week_bounds(self, ref_date: date | None = None) -> tuple[date, date]:
        """Retourne (lundi, dimanche) de la semaine ISO de ref_date."""
        ref = ref_date or date.today()
        monday = ref - timedelta(days=ref.weekday())
        sunday = monday + timedelta(days=6)
        return monday, sunday

    async def _count_active_suggestions_for_week(
        self, monday: date, sunday: date, athlete_id: int
    ) -> int:
        """Compte les suggestions actives (pending/accepted) de la semaine."""
        result = await self.db.execute(
            select(func.count(EditorialCalendarEntry.id)).where(
                EditorialCalendarEntry.source == "suggestion",
                EditorialCalendarEntry.content_type.in_(
                    ("story_souvenir", "story_edito")
                ),
                EditorialCalendarEntry.date >= monday,
                EditorialCalendarEntry.date <= sunday,
                EditorialCalendarEntry.status.in_(("pending", "accepted")),
            )
        )
        return result.scalar_one() or 0

    async def generate_weekly_suggestions(self) -> dict[str, Any]:
        """Génère exactement 3 suggestions pour la semaine ISO courante.

        Idempotente : si 3 suggestions actives existent déjà pour la semaine,
        ne crée rien. Retourne la liste des entrées créées/existantes.
        """
        return await self._generate_weekly_suggestions_inner()

    async def _generate_weekly_suggestions_inner(self) -> dict[str, Any]:
        """Corps de génération hebdomadaire (séparé pour le try/except externe)."""
        strategy = await self._get_strategy()
        if not strategy:
            raise ValueError("Stratégie éditoriale non configurée")

        athlete = await self._get_athlete()
        if not athlete:
            raise ValueError("Aucun athlète associé à l'utilisateur")

        monday, sunday = self._iso_week_bounds()

        existing_count = await self._count_active_suggestions_for_week(
            monday, sunday, athlete.id
        )
        if existing_count >= 3:
            # Déjà complètes : retourner les existantes sans rien créer
            return await self._list_week_suggestions(monday, sunday, athlete.id)

        to_create = 3 - existing_count

        # Contexte : activités anciennes et historique pour l'IA
        recent_activities = await self._get_recent_activities(athlete.id, limit=20)
        previous_suggestions = await self._get_previous_suggestions(athlete.id)

        # Génération IA des 3 sujets
        suggestions_data = await self._generate_suggestion_subjects(
            strategy, recent_activities, previous_suggestions, to_create
        )

        # Créer les entrées (dates réparties : mardi, jeudi, samedi)
        created_entries = []
        weekdays_iter = iter(_SUGGESTION_WEEKDAYS)
        for i, subject in enumerate(suggestions_data):
            # Trouver la prochaine date disponible dans la semaine
            target_weekday = next(weekdays_iter, _SUGGESTION_WEEKDAYS[i % 3])
            suggestion_date = monday + timedelta(
                days=(target_weekday - monday.weekday()) % 7
            )

            # Alternance souvenir / édito
            content_type = "story_souvenir" if i % 2 == 0 else "story_edito"

            entry = EditorialCalendarEntry(
                strategy_id=strategy.id,
                date=suggestion_date,
                topic=subject.get("title", "Suggestion de story"),
                theme=None,
                objective=subject.get("objectif", "engagement"),
                notes=subject.get("justification", ""),
                hashtags=subject.get("hashtags"),
                status="pending",
                content_type=content_type,
                source="suggestion",
                source_activity_id=None,
                photo_id=None,
            )
            self.db.add(entry)
            created_entries.append(entry)

        await self.db.commit()
        for entry in created_entries:
            await self.db.refresh(entry)

        return await self._list_week_suggestions(monday, sunday, athlete.id)

    async def _list_week_suggestions(
        self, monday: date, sunday: date, athlete_id: int
    ) -> dict[str, Any]:
        """Liste les suggestions de la semaine."""
        result = await self.db.execute(
            select(EditorialCalendarEntry)
            .where(
                EditorialCalendarEntry.source == "suggestion",
                EditorialCalendarEntry.content_type.in_(
                    ("story_souvenir", "story_edito")
                ),
                EditorialCalendarEntry.date >= monday,
                EditorialCalendarEntry.date <= sunday,
            )
            .order_by(EditorialCalendarEntry.date.asc())
        )
        entries = result.scalars().all()
        return {
            "week_monday": monday.isoformat(),
            "week_sunday": sunday.isoformat(),
            "suggestions": [
                {
                    "id": e.id,
                    "date": e.date.isoformat(),
                    "topic": e.topic,
                    "content_type": e.content_type,
                    "status": e.status,
                    "notes": e.notes,
                    "hashtags": e.hashtags,
                }
                for e in entries
            ],
        }

    async def accept_suggestion(self, entry_id: int) -> EditorialCalendarEntry | None:
        """Passe une suggestion en statut 'accepted' (modifiable dans le Studio)."""
        result = await self.db.execute(
            select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        if entry.source != "suggestion":
            return None
        entry.status = "accepted"
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def refuse_suggestion(self, entry_id: int) -> EditorialCalendarEntry | None:
        """Passe une suggestion en statut 'refused' (conservée, non supprimée)."""
        result = await self.db.execute(
            select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        if entry.source != "suggestion":
            return None
        entry.status = "refused"
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def reschedule_suggestion(
        self, entry_id: int, new_date: date
    ) -> EditorialCalendarEntry | None:
        """Reporte une suggestion à une nouvelle date."""
        result = await self.db.execute(
            select(EditorialCalendarEntry).where(EditorialCalendarEntry.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        if entry.source != "suggestion":
            return None
        entry.date = new_date
        entry.status = "pending"
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    # ------------------------------------------------------------------ #
    # Helpers privés
    # ------------------------------------------------------------------ #

    async def _get_recent_activities(
        self, athlete_id: int, limit: int = 20
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete_id)
            .order_by(SportActivity.started_at.desc())
            .limit(limit)
        )
        return [
            {
                "id": act.id,
                "activity_name": act.activity_name,
                "sport_type": act.sport_type,
                "started_at": act.started_at.isoformat() if act.started_at else None,
                "distance_m": act.distance_m,
                "elevation_gain_m": act.elevation_gain_m,
                "duration_seconds": act.duration_seconds,
            }
            for act in result.scalars().all()
        ]

    async def _get_previous_suggestions(
        self, athlete_id: int, limit: int = 30
    ) -> list[dict[str, Any]]:
        """Historique des suggestions pour éviter les doublons."""
        result = await self.db.execute(
            select(EditorialCalendarEntry)
            .where(
                EditorialCalendarEntry.source == "suggestion",
                EditorialCalendarEntry.content_type.in_(
                    ("story_souvenir", "story_edito")
                ),
            )
            .order_by(EditorialCalendarEntry.created_at.desc())
            .limit(limit)
        )
        return [
            {"topic": e.topic, "date": e.date.isoformat() if e.date else None}
            for e in result.scalars().all()
        ]

    async def _generate_suggestion_subjects(
        self,
        strategy: CommunityManagerStrategy,
        recent_activities: list[dict[str, Any]],
        previous_suggestions: list[dict[str, Any]],
        count: int,
    ) -> list[dict[str, str]]:
        """Appelle l'IA pour générer les sujets de suggestions.

        En cas d'échec (réseau, IA indisponible, parsing invalide),
        retourne des suggestions de fallback.
        """
        try:
            return await self._generate_suggestion_subjects_inner(
                strategy, recent_activities, previous_suggestions, count
            )
        except Exception as exc:
            logger.warning("[SUGGESTIONS] Échec génération sujets : %s", exc)
            return self._fallback_suggestions(count)

    async def _generate_suggestion_subjects_inner(
        self,
        strategy: CommunityManagerStrategy,
        recent_activities: list[dict[str, Any]],
        previous_suggestions: list[dict[str, Any]],
        count: int,
    ) -> list[dict[str, str]]:
        """Corps de génération des sujets (séparé pour le try/except externe)."""
        prompt = (
            f"Génère exactement {count} suggestions de stories Instagram pour un coureur à pied/trailer.\n"
            f"Contexte :\n"
            f"- Activités récentes : {recent_activities[:5]}\n"
            f"- Suggestions déjà proposées (éviter de les répéter) : {previous_suggestions[:10]}\n"
            f"- Stratégie : thèmes={strategy.themes}, objectifs={strategy.objectives}\n\n"
            f"Pour chaque suggestion, retourne un objet avec :\n"
            f"- title : titre court de la story\n"
            f"- objectif : engagement, visibility ou brand_awareness\n"
            f"- justification : pourquoi ce sujet est proposé (1 phrase)\n"
            f"- hashtags : 2-3 hashtags pertinents\n"
            f"Réponds uniquement en JSON avec la clé 'suggestions' (liste de {count} objets)."
        )

        response = await ai_gateway.generate(
            prompt=prompt,
            system_prompt=(
                "Tu es un expert community manager pour comptes Instagram sportifs. "
                "Propose des sujets de stories pertinents et originaux."
            ),
            temperature=0.7,
            max_tokens=1500,
        )

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
                payload = json.loads(cleaned[s : e + 1])
        except (json.JSONDecodeError, ValueError):
            payload = None

        if not isinstance(payload, dict) or not isinstance(
            payload.get("suggestions"), list
        ):
            return self._fallback_suggestions(count)

        subjects = []
        for item in payload["suggestions"][:count]:
            if not isinstance(item, dict):
                continue
            subjects.append(
                {
                    "title": str(item.get("title", "Story")).strip(),
                    "objectif": str(item.get("objectif", "engagement")).strip(),
                    "justification": str(item.get("justification", "")).strip(),
                    "hashtags": str(item.get("hashtags", "")).strip() or None,
                }
            )

        while len(subjects) < count:
            subjects.append(self._fallback_suggestions(1)[0])

        return subjects[:count]

    @staticmethod
    def _fallback_suggestions(count: int) -> list[dict[str, str]]:
        """Suggestions par défaut si l'IA est indisponible."""
        base = [
            {
                "title": "Souvenir d'une ancienne sortie",
                "objectif": "engagement",
                "justification": "Rappeler une belle sortie passée pour engager la communauté.",
                "hashtags": "#trail #souvenir",
            },
            {
                "title": "Conseil d'entraînement",
                "objectif": "visibility",
                "justification": "Partager un conseil utile sur l'entraînement.",
                "hashtags": "#entrainement #running",
            },
            {
                "title": "Objectif de la semaine",
                "objectif": "brand_awareness",
                "justification": "Afficher un objectif sportif pour la semaine à venir.",
                "hashtags": "#objectif #running",
            },
        ]
        return base[:count]
