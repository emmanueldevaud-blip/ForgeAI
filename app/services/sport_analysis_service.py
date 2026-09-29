"""Analyses sportives automatiques de ForgeAI.

Trois types d'analyses générées via l'AI Gateway centralisée :

* ``analyze_morning``      : bilan de récupération (heure configurable)
* ``analyze_evening``      : bilan de la journée (heure configurable)
* ``analyze_activity``     : débrief d'une activité Garmin (délai après sync)

Chaque analyse produit deux formats : une version courte destinée à la
notification téléphone (repliquée sur la montre Garmin Connect) et une
version complète stockée dans ForgeAI.

Garanties :

* idempotence : une seule analyse par athlète et par cible (contrainte
  unique ``athlete_id + dedupe_key``) ;
* isolation : un échec IA n'affecte jamais les activités ni la synchro ;
* passerelle : uniquement ``ai_gateway`` (aucun appel direct aux
  fournisseurs Groq / Gemini / OpenRouter).
"""

import json
import logging
import time
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.sport import SportActivity, SportAnalysis, SportAthlete, SportGarminConnection, SportHealthDaily
from app.models.user import User
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.notification import NotificationService
from app.services.sport import SportService
from app.services.sport_analysis import SportAnalysisEngine

logger = logging.getLogger(__name__)

# Une activité plus vieille que ce délai (import d'historique) n'est pas
# analysée automatiquement : seules les sorties récentes déclenchent une analyse.
ACTIVITY_ANALYSIS_MAX_AGE_HOURS = 48

_NOTIFICATION_CATEGORY = "sport_analysis"
_NOTIFICATION_URL = "/sport/analyses"
_NOTIFICATION_TITLES = {
    "morning": "Analyse du matin",
    "evening": "Analyse du soir",
    "activity": "Analyse de sortie",
}
_EMOJI = {"morning": "🌅", "evening": "🌙", "activity": "🏃"}

_SYSTEM_PROMPT = (
    "Tu es le Coach Sport de ForgeAI pour les analyses automatiques (matin, soir, sortie). "
    "Tu reçois uniquement des données d'entraînement et de santé (Garmin) au format JSON. "
    "Réponds STRICTEMENT par un objet JSON valide, sans texte avant ou après, sans balises Markdown, "
    "avec exactement ces clés : "
    '{"title": "titre court (80 caractères max)", '
    '"notification": "version courte pour notification téléphone/montre : 4 à 6 lignes maximum, '
    'chiffres clés puis verdict (effort, charge, récupération) avec ton coach", '
    '"summary": "résumé en 1 à 2 phrases", '
    '"content": "analyse complète en français structurée ainsi : ## Résumé / ## Points remarquables / '
    "## Charge et récupération / ## Comparaison avec l'historique / ## Conseil pour la suite\"} "
    "RÈGLES ABSOLUES :\n"
    "- UNIQUEMENT les données fournies (ne fabrique AUCUNE valeur absente).\n"
    "- En français, ton de coach sportif : sympathique, chaleureux, motivant, accessible, naturel, "
    "légèrement taquin, parfois décalé, complice avec l'utilisateur.\n"
    "- Distingue mesure et interprétation. Jamais de diagnostic médical.\n"
    "- Si une donnée manque, ne la mentionne pas.\n\n"
    "STYLE ET HUMOUR :\n"
    "- Phrases courtes, vocabulaire naturel, tutoiement, formulations directes.\n"
    "- Humour léger et intelligent présent régulièrement mais naturellement "
    "(~1 touche par analyse, 0 si contexte sérieux/fatigue, 2 si analyse longue).\n"
    "- Jeux de mots, métaphores sportives, autodérision, références trail/endurance occasionnelles "
    "(D+, cailloux, ravitaillement, sentiers, frontale, mental, bâtons).\n"
    "- Dosage : 70% coach / 20% analyse / 10% humour. L'humour est une épice, pas le plat principal.\n"
    "- Adapte l'humour : enthousiaste si belle séance, doux si séance dure, réduit si fatigue importante.\n"
    "- Quelques emojis modérés (🏃 ❤️ 💪 😄 ⛰️ 🔥 🧠 😴 ☕) quand ça apporte quelque chose.\n"
    "- PAS de félicitations vides (\"Bravo ! Super !\") : félicite sur la base des données.\n"
    "- Varie les ouvertures, évite les répétitions.\n"
    "- Structure préférée dans content : ## Résumé / ## Points remarquables / "
    "## Charge et récupération / ## Comparaison avec l'historique / ## Conseil pour la suite\n"
    "- La notification doit rester lisible sur une montre (concise, chiffres + verdict + touche coach)."
)

_MORNING_INSTRUCTION = (
    "Analyse du matin. Produis le bilan de récupération et d'état de forme à partir de la nuit et des "
    "jours précédents : sommeil (durée, qualité, phases, réveils), HRV, FC repos, stress, Body Battery, "
    "Training Readiness, comparaison avec les jours récents, puis un conseil pour la journée.\n\n"
    "TON SPÉCIFIQUE MATIN :\n"
    "- Ton humain dès le réveil, comme un coach qui passe prendre des nouvelles.\n"
    "- Exemple d'ouverture : \"☀️ Bonjour champion !\" ou variation naturelle.\n"
    "- Si récupération bonne : enthousiasme modéré, feu vert pour la journée.\n"
    "- Si récupération moyenne : rassurant, conseille d'adapter.\n"
    "- Si récupération mauvaise : humour très réduit, priorité récupération, bienveillance.\n"
    "- Termine par un conseil concret pour la journée.\n"
    "- Petite touche d'humour légère si le contexte s'y prête (ex: \"aucune montagne n'a été déclarée "
    "obligatoire avant le café ☕😄\").\n"
    "- Notification courte : chiffres clés (HRV, Body Battery, Readiness) + verdict + 1 phrase coach."
)

_EVENING_INSTRUCTION = (
    "Analyse du soir. Produis le bilan de la journée : activités (distance, durée, dénivelé, FC, allure), "
    "charge du jour, tendances récentes, état de récupération, puis un conseil pour la suite.\n\n"
    "TON SPÉCIFIQUE SOIR :\n"
    "- Bilan de la journée comme un coach qui fait le point avant le dîner.\n"
    "- Exemple d'ouverture : \"🌙 Bilan du jour\" ou variation naturelle.\n"
    "- Résume la charge du jour factuellement, puis interprétation.\n"
    "- Si journée bien gérée : satisfaction, validation.\n"
    "- Si journée lourde : explicatif, rassurant sur la récupération à venir.\n"
    "- Conseil concret pour la soirée/nuit (hydratation, repas, sommeil).\n"
    "- Petite touche d'humour légère si le contexte s'y prête "
    "(ex: \"rester allongé est une séance validée par le coach 😄\").\n"
    "- Notification courte : volume du jour + charge + verdict récupération + 1 phrase coach."
)

_ACTIVITY_INSTRUCTION = (
    "Analyse de sortie synchronisée depuis Garmin. Produis le débrief : durée, distance, allure ou vitesse, "
    "FC moyenne et maximale, dénivelé, cadence, puissance si disponibles, points remarquables de l'effort, "
    "comparaison avec les sorties similaires, charge et récupération attendue, puis un conseil concret.\n\n"
    "TON SPÉCIFIQUE SORTIE :\n"
    "- Débrief comme si on discutait après la douche, complice et factuel.\n"
    "- Ouvre variément : \"Ça, c'est une sortie propre.\", \"Les chiffres racontent une histoire sympa.\", "
    "\"Tiens, voilà quelque chose d'intéressant.\", \"Aujourd'hui le cardio avait décidé d'être raisonnable.\"\n"
    "- Belle séance : enthousiaste, souligne les points forts data-based.\n"
    "- Séance difficile : humour doux, explicatif, jamais culpabilisant.\n"
    "- Fatigue importante : humour réduit, priorité récupération.\n"
    "- Grosse perf : enthousiaste mais factuel (\"les chiffres sont de la partie\").\n"
    "- Vocabulaire trail/endurance occasionnel bienvenu (D+, cailloux, sentiers, ravitaillement, mental...).\n"
    "- Compare avec l'historique : tendances > donnée isolée.\n"
    "- Structure content : ## Résumé / ## Points remarquables / ## Charge et récupération / "
    "## Comparaison avec l'historique / ## Conseil pour la suite\n"
    "- Notification courte : distance, durée, D+, FC moy + verdict effort + 1 phrase coach (lisible montre)."
)


def _parse_time(value: str) -> datetime_time | None:
    try:
        return datetime.strptime((value or "").strip(), "%H:%M").time()
    except ValueError:
        logger.warning("[SPORT-ANALYSIS] Heure invalide ignorée: %r (format attendu HH:MM)", value)
        return None


def _naive_utc(value: datetime) -> datetime:
    """Date/heure UTC naïve pour les comparaisons SQL (SQLite/MySQL)."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_json_answer(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if not isinstance(content, str) or not content.strip():
        return None
    return payload


def _shorten(text: str, limit: int = 500) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    short = "\n".join(lines[:6])
    return short if len(short) <= limit else short[: limit - 1] + "…"


class SportAnalysisService:
    """Génère et stocke les analyses sportives automatiques d'un utilisateur."""

    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.sport = SportService(db, current_user)

    # ------------------------------------------------------------------ #
    # Analyses
    # ------------------------------------------------------------------ #

    async def analyze_morning(self) -> tuple[bool, SportAnalysis | None]:
        """(nouvelle_analyse, analyse) — idempotente par jour et par athlète."""
        return await self._analyze_daily("morning", _MORNING_INSTRUCTION, self._morning_context)

    async def morning_sleep_available(self) -> bool:
        """Vrai si la nuit dernière figure déjà dans les données du jour.

        Garmin date le sommeil par le jour de réveil : la nuit écoulée est
        rangée sous aujourd'hui une fois synchronisée. Tant qu'elle manque,
        l'analyse du matin patiente (sinon elle décrirait la nuit d'avant).
        """
        athlete = await self.sport.get_or_create_athlete()
        health_json = await self.db.scalar(
            select(SportHealthDaily.health_json).where(
                SportHealthDaily.athlete_id == athlete.id,
                SportHealthDaily.day == self._local_today(),
            )
        )
        return bool(health_json and health_json.get("sleep"))

    async def analyze_evening(self) -> tuple[bool, SportAnalysis | None]:
        return await self._analyze_daily("evening", _EVENING_INSTRUCTION, self._evening_context)

    async def _analyze_daily(self, analysis_type: str, instruction: str, context_builder) -> tuple[bool, SportAnalysis | None]:
        athlete = await self.sport.get_or_create_athlete()
        day = self._local_today()
        dedupe_key = f"{analysis_type}:{day.isoformat()}"
        existing = await self._find(athlete, dedupe_key)
        if existing is not None:
            await self._notify(athlete, existing, analysis_type)
            return False, existing
        try:
            context = await context_builder(athlete, day)
        except Exception:
            logger.exception("[SPORT-ANALYSIS] Contexte %s indisponible", analysis_type)
            return False, None
        generated = await self._generate(instruction, context)
        if generated is None:
            return False, None
        return await self._store(
            athlete,
            analysis_type=analysis_type,
            activity_id=None,
            analysis_day=day,
            dedupe_key=dedupe_key,
            generated=generated,
        )

    async def analyze_activity(self, activity_id: int) -> tuple[bool, SportAnalysis | None]:
        """Analyse automatique d'une activité (une seule fois par activité)."""
        athlete = await self.sport.get_or_create_athlete()
        activity = await self.db.scalar(
            select(SportActivity).where(
                SportActivity.id == activity_id, SportActivity.athlete_id == athlete.id
            )
        )
        if activity is None:
            return False, None
        dedupe_key = f"activity:{activity.id}"
        existing = await self._find(athlete, dedupe_key)
        if existing is not None:
            await self._notify(athlete, existing, "activity")
            return False, existing
        context = await self.sport.build_activity_ai_context(activity.id)
        if context is None:
            return False, None
        context = {"type": "activity", **context}
        generated = await self._generate(_ACTIVITY_INSTRUCTION, context)
        if generated is None:
            return False, None
        return await self._store(
            athlete,
            analysis_type="activity",
            activity_id=activity.id,
            analysis_day=activity.started_at.date(),
            dedupe_key=dedupe_key,
            generated=generated,
        )

    async def analyze_recent_activities(self, now: datetime | None = None) -> int:
        """Analyse les activités Garmin récemment synchronisées (après délai).

        Une activité n'est analysée qu'une seule fois ; elle doit être
        terminée, synchronisée depuis plus de ``SPORT_ACTIVITY_ANALYSIS_DELAY_MINUTES``
        et avoir débuté dans les 48 dernières heures.
        """
        settings = get_settings()
        now = now or datetime.now(timezone.utc)
        delay = timedelta(minutes=max(0, settings.SPORT_ACTIVITY_ANALYSIS_DELAY_MINUTES))
        oldest = now - timedelta(hours=ACTIVITY_ANALYSIS_MAX_AGE_HOURS)
        athlete = await self.sport.get_or_create_athlete()
        result = await self.db.execute(
            select(SportActivity).where(
                SportActivity.athlete_id == athlete.id,
                SportActivity.source_type == "garmin",
                SportActivity.created_at <= _naive_utc(now - delay),
                SportActivity.created_at >= _naive_utc(oldest),
                SportActivity.started_at >= _naive_utc(oldest),
            ).order_by(SportActivity.started_at.asc())
        )
        activities = list(result.scalars().all())
        if not activities:
            return 0
        analyzed_ids = {
            row.activity_id
            for row in (
                await self.db.execute(
                    select(SportAnalysis).where(
                        SportAnalysis.athlete_id == activities[0].athlete_id,
                        SportAnalysis.analysis_type == "activity",
                        SportAnalysis.activity_id.in_([item.id for item in activities]),
                    )
                )
            ).scalars()
            if row.activity_id is not None
        }
        created = 0
        for activity in activities:
            if activity.id in analyzed_ids:
                continue
            if self._ends_at(activity) > _naive_utc(now):
                continue  # l'activité n'est pas encore terminée
            was_created, _ = await self.analyze_activity(activity.id)
            if was_created:
                created += 1
        return created

    @staticmethod
    def _ends_at(activity: SportActivity) -> datetime:
        started = _naive_utc(activity.started_at)
        return started + timedelta(seconds=activity.duration_seconds or 0)

    # ------------------------------------------------------------------ #
    # Contextes
    # ------------------------------------------------------------------ #

    async def _morning_context(self, athlete: SportAthlete, day: date) -> dict[str, Any]:
        return {
            "type": "morning",
            "date": day.isoformat(),
            "recovery": await self.sport.recovery_context(),
            "health_7_days": await self.sport.health_context(7),
            "training_14_days": SportAnalysisEngine.summarize(
                await self._recent_activities(athlete, 14)
            ),
        }

    async def _evening_context(self, athlete: SportAthlete, day: date) -> dict[str, Any]:
        return {
            "type": "evening",
            "date": day.isoformat(),
            "day_analysis": await self.sport.analyze_day(day),
            "health_7_days": await self.sport.health_context(7),
            "recovery": await self.sport.recovery_context(),
            "training_7_days": SportAnalysisEngine.summarize(
                await self._recent_activities(athlete, 7)
            ),
        }

    async def _recent_activities(self, athlete: SportAthlete, days: int) -> list[SportActivity]:
        day = self._local_today()
        start = _naive_utc(datetime.combine(day - timedelta(days=days - 1), datetime.min.time()))
        result = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id, SportActivity.started_at >= start)
            .order_by(SportActivity.started_at.desc())
            .limit(50)
        )
        return list(result.scalars().all())

    @staticmethod
    def _local_today() -> date:
        settings = get_settings()
        try:
            tz = ZoneInfo(settings.SPORT_ANALYSIS_TIMEZONE)
        except Exception:
            tz = timezone.utc
        return datetime.now(tz).date()

    # ------------------------------------------------------------------ #
    # Génération IA (exclusivement via l'AI Gateway)
    # ------------------------------------------------------------------ #

    async def _generate(self, instruction: str, context: dict[str, Any]) -> dict[str, Any] | None:
        prompt = (
            f"{instruction}\n\nDonnées (JSON) :\n"
            f"{json.dumps(context, ensure_ascii=False, default=str)}"
        )
        started = time.monotonic()
        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.4,
                max_tokens=1400,
            )
        except AIGatewayError as exc:
            # Un échec IA n'affecte jamais les données : simple journal, retenté plus tard.
            logger.warning("[SPORT-ANALYSIS] AI Gateway indisponible (%s) : %s", type(exc).__name__, exc)
            return None
        duration_ms = int((time.monotonic() - started) * 1000)
        text = (response.text or "").strip()
        if not text:
            logger.warning("[SPORT-ANALYSIS] Réponse IA vide")
            return None
        payload = _parse_json_answer(text)
        if payload is None:
            # Repli : la réponse brute devient l'analyse complète.
            payload = {"content": text, "summary": _shorten(text, 300), "notification": _shorten(text)}
        payload.setdefault("title", "Analyse Sport")
        payload.setdefault("notification", _shorten(str(payload.get("summary") or payload["content"])))
        payload.setdefault("summary", _shorten(str(payload["content"]), 300))
        payload["_meta"] = {
            "provider": getattr(response, "provider_used", None),
            "model": getattr(response, "model_used", None),
            "duration_ms": duration_ms,
            "fallback_used": bool(getattr(response, "fallback_used", False)),
        }
        return payload

    # ------------------------------------------------------------------ #
    # Persistance + notification
    # ------------------------------------------------------------------ #

    async def _find(self, athlete: SportAthlete, dedupe_key: str) -> SportAnalysis | None:
        return await self.db.scalar(
            select(SportAnalysis).where(
                SportAnalysis.athlete_id == athlete.id, SportAnalysis.dedupe_key == dedupe_key
            )
        )

    async def _store(
        self,
        athlete: SportAthlete,
        *,
        analysis_type: str,
        activity_id: int | None,
        analysis_day: date,
        dedupe_key: str,
        generated: dict[str, Any],
    ) -> tuple[bool, SportAnalysis | None]:
        meta = generated.get("_meta") or {}
        analysis = SportAnalysis(
            athlete_id=athlete.id,
            activity_id=activity_id,
            analysis_type=analysis_type,
            analysis_day=analysis_day,
            dedupe_key=dedupe_key,
            title=str(generated.get("title") or "Analyse Sport")[:200],
            summary=str(generated.get("summary") or ""),
            content=str(generated.get("content") or ""),
            provider=meta.get("provider"),
            model=meta.get("model"),
            duration_ms=meta.get("duration_ms"),
            fallback_used=bool(meta.get("fallback_used")),
            notification_sent=False,
        )
        self.db.add(analysis)
        try:
            await self.db.flush()
        except IntegrityError:
            # Course avec un autre cycle : l'analyse existe déjà, rien à faire.
            await self.db.rollback()
            return False, await self._find(athlete, dedupe_key)
        await self.db.commit()
        await self._notify(athlete, analysis, analysis_type)
        return True, analysis

    async def _notify(self, athlete: SportAthlete, analysis: SportAnalysis, analysis_type: str) -> None:
        if analysis.notification_sent or not athlete.user_id:
            return
        title = f"{_EMOJI.get(analysis_type, '')} {_NOTIFICATION_TITLES.get(analysis_type, 'Analyse Sport')}".strip()
        try:
            await NotificationService(self.db).send(
                user_id=athlete.user_id,
                title=title,
                message=analysis.summary or analysis.title,
                category=_NOTIFICATION_CATEGORY,
                data={
                    "url": _NOTIFICATION_URL,
                    "analysis_id": analysis.id,
                    "analysis_type": analysis.analysis_type,
                },
            )
            analysis.notification_sent = True
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            logger.exception(
                "[SPORT-ANALYSIS] Notification impossible (analyse %s conservée)", analysis.id
            )


# ---------------------------------------------------------------------- #
# Cycle planifié (boucle de app.main)
# ---------------------------------------------------------------------- #


async def run_sport_analysis_cycle(db: AsyncSession, now: datetime | None = None) -> dict[str, Any]:
    """Exécute les analyses dues : matin, soir et activités récentes.

    Appelée en boucle par l'application ; conçue pour être rappelée
    fréquemment : l'idempotence en base garantit qu'une analyse n'est
    générée qu'une seule fois.
    """
    settings = get_settings()
    stats: dict[str, Any] = {
        "status": "ok",
        "morning": 0,
        "evening": 0,
        "activities": 0,
        "errors": 0,
    }
    if not settings.SPORT_ANALYSIS_ENABLED:
        stats["status"] = "disabled"
        return stats

    try:
        tz = ZoneInfo(settings.SPORT_ANALYSIS_TIMEZONE)
    except Exception:
        tz = timezone.utc
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    local_time = now.astimezone(tz).time()

    morning_time = _parse_time(settings.SPORT_MORNING_ANALYSIS_TIME)
    evening_time = _parse_time(settings.SPORT_EVENING_ANALYSIS_TIME)
    morning_deadline = _parse_time(settings.SPORT_MORNING_ANALYSIS_DEADLINE)
    valid_window = morning_time is not None and evening_time is not None
    morning_due = bool(
        settings.SPORT_MORNING_ANALYSIS_ENABLED
        and valid_window
        and morning_time <= local_time < evening_time
    )
    evening_due = bool(
        settings.SPORT_EVENING_ANALYSIS_ENABLED
        and valid_window
        and local_time >= evening_time
    )
    activity_due = bool(settings.SPORT_ACTIVITY_ANALYSIS_ENABLED)
    if not morning_due and not evening_due and not activity_due:
        stats["status"] = "idle"
        return stats

    result = await db.execute(
        select(SportAthlete)
        .join(SportGarminConnection)
        .where(SportGarminConnection.status == "connected")
    )
    for athlete in result.scalars().all():
        if not athlete.user_id:
            continue
        user = await db.get(User, athlete.user_id)
        if user is None or not user.is_active:
            continue
        service = SportAnalysisService(db, user)
        if morning_due and await _morning_ready(service, morning_deadline, local_time):
            stats["errors"] += await _run_quietly(stats, "morning", service.analyze_morning)
        if evening_due:
            stats["errors"] += await _run_quietly(stats, "evening", service.analyze_evening)
        if activity_due:
            try:
                stats["activities"] += await service.analyze_recent_activities(now)
            except Exception:
                stats["errors"] += 1
                logger.exception("[SPORT-ANALYSIS] Échec analyse d'activités (user %s)", user.id)
    return stats


async def _morning_ready(
    service: SportAnalysisService, deadline: datetime_time | None, local_time: datetime_time
) -> bool:
    """L'analyse du matin attend la nuit synchronisée, au plus tard à la deadline.

    Sans deadline valide, comportement historique : génération dès l'ouverture
    de la fenêtre du matin.
    """
    if deadline is None or local_time >= deadline:
        return True
    return await service.morning_sleep_available()


async def _run_quietly(stats: dict[str, Any], key: str, coroutine_factory) -> int:
    """Lance une analyse en isolant toute erreur ; retourne 1 si erreur."""
    try:
        created, _ = await coroutine_factory()
    except Exception:
        logger.exception("[SPORT-ANALYSIS] Échec analyse %s", key)
        return 1
    if created:
        stats[key] += 1
    return 0
