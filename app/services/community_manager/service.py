"""Service cœur du Community Manager IA."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.module import Module, ModuleConfig
from app.models.sport import CommunityManagerStrategy, EditorialCalendarEntry, SportActivity, SportAthlete
from app.models.user import User
from app.schemas.sport import (
    CalendarGenerateRequest,
    CalendarGenerateResponse,
    CommunityManagerStrategyCreate,
    CommunityManagerStrategyResponse,
    CommunityManagerStrategyUpdate,
    EditorialCalendarEntryCreate,
    EditorialCalendarEntryResponse,
    EditorialCalendarEntryUpdate,
    COMMUNITY_MANAGER_THEMES,
    COMMUNITY_MANAGER_OBJECTIVES,
    CALENDAR_ENTRY_STATUSES,
)
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.community_manager.prompts import SYSTEM_PROMPT, build_generation_prompt

logger = logging.getLogger(__name__)

COMMUNITY_MANAGER_MODULE_CODE = "community_manager"

# Lock pour éviter les générations concurrentes par athlète
_generation_locks: dict[int, Any] = {}

try:
    import asyncio
except ImportError:
    asyncio = None


class CommunityManagerService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    async def _get_athlete(self) -> SportAthlete | None:
        """Récupère l'athlète associé à l'utilisateur courant."""
        result = await self.db.execute(
            select(SportAthlete).where(SportAthlete.user_id == self.current_user.id)
        )
        return result.scalar_one_or_none()

    async def _get_or_create_athlete(self) -> SportAthlete:
        """Récupère ou crée l'athlète pour l'utilisateur courant."""
        athlete = await self._get_athlete()
        if athlete is None:
            athlete = SportAthlete(user_id=self.current_user.id)
            self.db.add(athlete)
            await self.db.flush()
            await self.db.refresh(athlete)
        return athlete

    async def get_strategy(self) -> CommunityManagerStrategy | None:
        """Récupère la stratégie éditoriale de l'athlète."""
        athlete = await self._get_athlete()
        if not athlete:
            return None
        result = await self.db.execute(
            select(CommunityManagerStrategy)
            .where(CommunityManagerStrategy.athlete_id == athlete.id)
            .options(selectinload(CommunityManagerStrategy.calendar_entries))
        )
        return result.scalar_one_or_none()

    async def create_or_update_strategy(
        self, data: CommunityManagerStrategyCreate | CommunityManagerStrategyUpdate
    ) -> CommunityManagerStrategy:
        """Crée ou met à jour la stratégie éditoriale."""
        athlete = await self._get_or_create_athlete()

        result = await self.db.execute(
            select(CommunityManagerStrategy).where(CommunityManagerStrategy.athlete_id == athlete.id)
        )
        strategy = result.scalar_one_or_none()

        if strategy is None:
            strategy = CommunityManagerStrategy(athlete_id=athlete.id)
            self.db.add(strategy)

        # Mettre à jour les champs
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(strategy, field, value)

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(strategy)
        return strategy

    async def _get_recent_activities(self, limit: int = 20) -> list[dict[str, Any]]:
        """Récupère les activités récentes de l'athlète pour le contexte IA."""
        athlete = await self._get_athlete()
        if not athlete:
            return []

        result = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id)
            .order_by(SportActivity.started_at.desc())
            .limit(limit)
        )
        activities = result.scalars().all()

        return [
            {
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
            }
            for act in activities
        ]

    async def generate_calendar(self, request: CalendarGenerateRequest) -> CalendarGenerateResponse:
        """Génère un calendrier éditorial via l'IA."""
        # Récupérer l'athlète de l'utilisateur courant (ne pas faire confiance à l'athlete_id du frontend)
        athlete = await self._get_athlete()
        if not athlete:
            raise ValueError("Aucun athlète associé à l'utilisateur")

        # Vérifier si l'utilisateur est admin pour accès transversal (optionnel)
        # Pour l'instant, on restreint strictement à son propre athlète
        # TODO: ajouter vérification permission admin si nécessaire

        # Protection contre la génération concurrente pour le même athlète
        lock = _get_generation_lock(athlete.id)
        async with lock:
            # Récupérer la stratégie
            strategy = await self.get_strategy()
            if not strategy:
                raise ValueError("Stratégie éditoriale non configurée. Veuillez d'abord configurer la stratégie.")

            # Récupérer les activités récentes
            recent_activities = await self._get_recent_activities()

            # Construire le prompt avec données sanitizées
            prompt = build_generation_prompt(
                strategy=_sanitize_strategy_for_prompt(strategy),
                recent_activities=recent_activities,
                count=request.count,
            )

            # Appeler l'IA
            try:
                response = await ai_gateway.generate(
                    prompt=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    temperature=0.7,
                    max_tokens=2000,
                )
            except AIGatewayError as exc:
                logger.warning("[COMMUNITY-MANAGER] IA indisponible : %s", exc)
                raise

            # Parser la réponse JSON de manière robuste
            payload = _parse_ai_json_response(response.text)
            if not isinstance(payload, dict) or not isinstance(payload.get("calendar"), list):
                raise ValueError("Réponse IA invalide (structure inattendue)")

            # Créer les entrées de calendrier en statut "brouillon" avec validation
            calendar_entries = []
            for item in payload["calendar"][: request.count]:
                if not isinstance(item, dict):
                    continue

                # Valider et sanitizer les champs
                validated_entry = _validate_and_sanitize_entry(item, strategy)
                if validated_entry is None:
                    continue

                entry = EditorialCalendarEntry(
                    strategy_id=strategy.id,
                    date=validated_entry["date"],
                    topic=validated_entry["topic"],
                    theme=validated_entry["theme"],
                    objective=validated_entry["objective"],
                    notes=validated_entry["notes"],
                    hashtags=validated_entry["hashtags"],
                    status="brouillon",
                )
                self.db.add(entry)
                calendar_entries.append(entry)

            await self.db.flush()

            # Convertir en réponse
            response_entries = []
            for entry in calendar_entries:
                await self.db.refresh(entry)
                response_entries.append(
                    EditorialCalendarEntryResponse.model_validate(entry)
                )

            await self.db.commit()
            return CalendarGenerateResponse(calendar=response_entries)

    async def get_calendar(self) -> list[EditorialCalendarEntryResponse]:
        """Récupère le calendrier éditorial existant."""
        strategy = await self.get_strategy()
        if not strategy:
            return []

        result = await self.db.execute(
            select(EditorialCalendarEntry)
            .where(EditorialCalendarEntry.strategy_id == strategy.id)
            .order_by(EditorialCalendarEntry.date.asc())
        )
        entries = result.scalars().all()
        return [EditorialCalendarEntryResponse.model_validate(e) for e in entries]

    async def update_calendar_entry(
        self, entry_id: int, data: EditorialCalendarEntryUpdate
    ) -> EditorialCalendarEntryResponse | None:
        """Met à jour une entrée du calendrier (validation, refus, modification)."""
        strategy = await self.get_strategy()
        if not strategy:
            return None

        result = await self.db.execute(
            select(EditorialCalendarEntry).where(
                EditorialCalendarEntry.id == entry_id,
                EditorialCalendarEntry.strategy_id == strategy.id,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return None

        update_data = data.model_dump(exclude_unset=True)
        
        # Interdire la modification de strategy_id (sécurité)
        update_data.pop("strategy_id", None)
        
        # Valider les valeurs d'énumération si fournies
        if "theme" in update_data and update_data["theme"] and update_data["theme"] not in COMMUNITY_MANAGER_THEMES:
            raise ValueError(f"Thème invalide: {update_data['theme']}")
        if "objective" in update_data and update_data["objective"] and update_data["objective"] not in COMMUNITY_MANAGER_OBJECTIVES:
            raise ValueError(f"Objectif invalide: {update_data['objective']}")
        if "status" in update_data and update_data["status"] and update_data["status"] not in CALENDAR_ENTRY_STATUSES:
            raise ValueError(f"Statut invalide: {update_data['status']}")
        
        # Valider forbidden_topics si topic ou notes modifiés
        if "topic" in update_data or "notes" in update_data:
            topic = update_data.get("topic", entry.topic) or ""
            notes = update_data.get("notes", entry.notes) or ""
            check_text = f"{topic} {notes}".lower()
            for forbidden_topic in (strategy.forbidden_topics or []):
                if forbidden_topic and forbidden_topic.lower() in check_text:
                    raise ValueError(f"Sujet interdit détecté: {forbidden_topic}")

        for field, value in update_data.items():
            setattr(entry, field, value)

        await self.db.flush()
        await self.db.commit()
        await self.db.refresh(entry)
        return EditorialCalendarEntryResponse.model_validate(entry)

    async def delete_calendar_entry(self, entry_id: int) -> bool:
        """Supprime une entrée du calendrier (refus)."""
        strategy = await self.get_strategy()
        if not strategy:
            return False

        result = await self.db.execute(
            select(EditorialCalendarEntry).where(
                EditorialCalendarEntry.id == entry_id,
                EditorialCalendarEntry.strategy_id == strategy.id,
            )
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return False

        await self.db.delete(entry)
        await self.db.commit()
        return True


async def get_community_manager_config(db: AsyncSession) -> dict[str, Any]:
    """Récupère la configuration du module community_manager depuis ModuleConfig."""
    result = await db.execute(
        select(ModuleConfig)
        .join(Module)
        .where(Module.code == COMMUNITY_MANAGER_MODULE_CODE)
    )
    configs = result.scalars().all()
    return {config.key: config.value for config in configs if config.value is not None}


# ============================================================
# Fonctions utilitaires privées
# ============================================================

def _get_generation_lock(athlete_id: int) -> Any:
    """Retourne un verrou asyncio pour éviter les générations concurrentes."""
    if asyncio is None:
        # Fallback si asyncio non disponible (ne devrait pas arriver)
        class DummyLock:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
        return DummyLock()
    
    if athlete_id not in _generation_locks:
        _generation_locks[athlete_id] = asyncio.Lock()
    return _generation_locks[athlete_id]


def _sanitize_strategy_for_prompt(strategy: CommunityManagerStrategy) -> dict[str, Any]:
    """Sanitize les champs de stratégie avant injection dans le prompt pour prévenir l'injection."""
    def sanitize_string(value: Optional[str], max_len: int = 500) -> str:
        if not value:
            return "Non définie"
        # Échapper les caractères potentiellement dangereux pour l'injection de prompt
        sanitized = str(value).replace("\n", " ").replace("\r", " ").replace("{", "").replace("}", "")
        return sanitized[:max_len]
    
    def sanitize_list(value: list[str], max_items: int = 20, max_len: int = 100) -> list[str]:
        if not value:
            return []
        sanitized = []
        for item in value[:max_items]:
            if isinstance(item, str):
                clean = item.replace("\n", " ").replace("\r", " ").replace("{", "").replace("}", "")
                sanitized.append(clean[:max_len])
        return sanitized
    
    return {
        "brand_identity": sanitize_string(strategy.brand_identity, 200),
        "tone": sanitize_list(strategy.tone),
        "target_audience": sanitize_string(strategy.target_audience, 1000),
        "objectives": sanitize_list(strategy.objectives),
        "themes": sanitize_list(strategy.themes),
        "frequency": strategy.frequency if isinstance(strategy.frequency, int) and 1 <= strategy.frequency <= 14 else 3,
        "networks": sanitize_list(strategy.networks),
        "rules": sanitize_list(strategy.rules, max_len=200),
        "forbidden_topics": sanitize_list(strategy.forbidden_topics, max_len=100),
    }


def _parse_ai_json_response(text: str) -> dict[str, Any] | None:
    """Parse robustement la réponse JSON de l'IA."""
    if not text:
        return None
    
    cleaned = text.strip()
    
    # Retirer les blocs markdown
    if cleaned.startswith("```"):
        parts = cleaned.split("```")
        if len(parts) >= 3:
            cleaned = parts[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
    
    # Tenter de trouver un objet JSON valide
    # Stratégie 1: objet complet
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Stratégie 2: extraire le premier objet JSON complet
    brace_count = 0
    start_idx = -1
    for i, char in enumerate(cleaned):
        if char == '{':
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == '}':
            brace_count -= 1
            if brace_count == 0 and start_idx >= 0:
                try:
                    return json.loads(cleaned[start_idx:i+1])
                except json.JSONDecodeError:
                    continue
    
    # Stratégie 3: dernier essai avec find/rfind
    try:
        s, e = cleaned.find("{"), cleaned.rfind("}")
        if s >= 0 and e > s:
            return json.loads(cleaned[s:e+1])
    except (json.JSONDecodeError, ValueError):
        pass
    
    logger.error("[COMMUNITY-MANAGER] Impossible de parser la réponse IA: %s", text[:500])
    return None


def _validate_and_sanitize_entry(item: dict[str, Any], strategy: CommunityManagerStrategy) -> dict[str, Any] | None:
    """Valide et sanitize une entrée de calendrier générée par l'IA."""
    # Topic requis
    topic = (item.get("topic") or "").strip()
    if not topic:
        return None
    if len(topic) > 500:
        topic = topic[:500]
    
    # Date
    date_str = item.get("date")
    try:
        entry_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else datetime.now(timezone.utc).date()
    except (ValueError, TypeError):
        entry_date = datetime.now(timezone.utc).date()
    
    # Theme - valider contre les thèmes autorisés
    theme = item.get("theme")
    if theme and theme not in COMMUNITY_MANAGER_THEMES:
        logger.warning("[COMMUNITY-MANAGER] Thème IA invalide: %s", theme)
        theme = None
    
    # Objective - valider contre les objectifs autorisés
    objective = item.get("objective")
    if objective and objective not in COMMUNITY_MANAGER_OBJECTIVES:
        logger.warning("[COMMUNITY-MANAGER] Objectif IA invalide: %s", objective)
        objective = None
    
    # Notes
    notes = item.get("notes")
    if notes and not isinstance(notes, str):
        notes = str(notes)
    if notes and len(notes) > 2000:
        notes = notes[:2000]
    
    # Hashtags
    hashtags = item.get("hashtags")
    if hashtags and not isinstance(hashtags, str):
        hashtags = str(hashtags)
    if hashtags and len(hashtags) > 500:
        hashtags = hashtags[:500]
    
    # Vérifier les sujets interdits dans le topic et les notes
    forbidden = strategy.forbidden_topics or []
    check_text = f"{topic} {notes or ''}".lower()
    for forbidden_topic in forbidden:
        if forbidden_topic and forbidden_topic.lower() in check_text:
            logger.warning("[COMMUNITY-MANAGER] Sujet interdit détecté: %s", forbidden_topic)
            return None
    
    # Vérifier les règles (basique - présence de mots-clés)
    rules = strategy.rules or []
    for rule in rules:
        if rule and rule.lower() in check_text:
            logger.info("[COMMUNITY-MANAGER] Règle déclenchée: %s", rule)
    
    return {
        "date": entry_date,
        "topic": topic,
        "theme": theme,
        "objective": objective,
        "notes": notes,
        "hashtags": hashtags,
    }