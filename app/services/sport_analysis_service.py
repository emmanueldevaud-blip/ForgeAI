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
from app.models.sport import (
    SportActivity,
    SportAnalysis,
    SportAthlete,
    SportGarminConnection,
    SportHealthDaily,
)
from app.models.user import User
from app.services import coach_feed
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.notification import NotificationService
from app.services.sport import SportService
from app.services.sport_analysis import SportAnalysisEngine
from app.services.sport_personality import COACH_PERSONALITY

logger = logging.getLogger(__name__)

# Une activité plus vieille que ce délai (import d'historique) n'est pas
# analysée automatiquement : seules les sorties récentes déclenchent une analyse.
ACTIVITY_ANALYSIS_MAX_AGE_HOURS = 48

# L'Agent Sport ne se réveille pas pour un même déclencheur plus d'une fois
# par cet intervalle : la boucle du cycle tourne toutes les minutes.
AGENT_TRIGGER_COOLDOWN_MINUTES = 30

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
    '{"title": "titre court (80 caracteres max)", '
    '"notification": "version courte pour notification telephone/montre : 4 a 6 lignes MAXIMUM, '
    'format : 1 ligne distance/duree, 1 ligne charge, 1 ligne recuperation, 1 ligne verdict coach. '
    'PAS de phrases longues, PAS de details, PAS de liste a puces.", '
    '"summary": "resume en 1 a 2 phrases maximum", '
    '"content": "analyse complete en francais structuree EXACTEMENT avec ces 5 sections MARKDOWN : '
    '## Resume\\n## Points remarquables\\n## Charge et recuperation\\n'
    '## Comparaison avec l\'historique\\n## Conseil pour la suite. '
    'Chaque section doit etre presente, separee par une ligne vide."} '
    "REGLES ABSOLUES :\n"
    "- UNIQUEMENT les donnees fournies (ne fabrique AUCUNE valeur absente).\n"
    "- Si une donnee manque, ne la mentionne pas.\n\n"
    f"{COACH_PERSONALITY}\n\n"
    "Structure OBLIGATOIRE dans content (5 sections, dans l'ordre, separees par ligne vide) :\n"
    "## Resume\n"
    "## Points remarquables\n"
    "## Charge et recuperation\n"
    "## Comparaison avec l'historique\n"
    "## Conseil pour la suite\n"
    "La notification doit tenir sur une montre : 4 lignes max, concis, chiffres + verdict."
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
    "- Notification courte : chiffres clés (HRV, Body Battery, Readiness) + verdict + 1 phrase coach.\n\n"
    "SOMMEIL (règle stricte) :\n"
    "- recovery.latest.sleep_score / sleep_total_minutes décrivent UNIQUEMENT la nuit écoulée "
    "(jour de réveil = recovery.sleep_day, égal à recovery.reference_day) ; recovery.sleep_available "
    "indique si cette nuit est bien synchronisée.\n"
    "- Si recovery.sleep_available est false : le sommeil de la nuit dernière n'est pas disponible "
    "(recovery.sleep_unavailable_reason le précise). Annonce clairement « Données de sommeil non "
    "disponibles » (avec la raison si utile) et ne présente JAMAIS le sommeil du jour précédent "
    "comme celui de la nuit dernière.\n"
    "- Les lignes de health_7_days sont datées (colonne day) : la nuit écoulée figure uniquement sur "
    "la ligne du jour de référence ; ne prends jamais la ligne précédente à sa place.\n\n"
    "BODY BATTERY (règle stricte) :\n"
    "- recovery.latest.body_battery est la dernière valeur enregistrée, datée de "
    "recovery.latest.body_battery_day : c'est souvent la fin de journée de la veille.\n"
    "- recovery.body_battery_today n'est renseigné que si le Body Battery du jour est déjà synchronisé, "
    "sinon il vaut null : la valeur du réveil n'est alors pas disponible.\n"
    "- Si body_battery_today est null, dis-le clairement (« Body Battery du jour pas encore synchronisé ; "
    "valeur de fin de journée du JJ/MM : X % ») et ne présente JAMAIS cette valeur comme celle du réveil.\n"
    "- Ne recopie JAMAIS un autre chiffre du contexte (HRV, éveil, pas, stress...) comme Body Battery.\n"
    "- Toute donnée latest est datée : si elle ne provient pas de la nuit écoulée ou d'aujourd'hui, "
    "précise de quel jour elle vient au lieu de la présenter comme actuelle."
    "STRUCTURE CONTENT (5 sections MARKDOWN, dans l'ordre, séparées par ligne vide) : "
    "## Résumé / ## Points remarquables / ## Charge et récupération / ## Comparaison avec l'historique / ## Conseil pour la suite"
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
    "- Notification courte : volume du jour + charge + verdict récupération + 1 phrase coach.\n\n"
    "SOMMEIL (règle stricte) :\n"
    "- recovery.latest.sleep_* porte sur la nuit terminée ce matin (jour de réveil = recovery.sleep_day).\n"
    "- Si recovery.sleep_available est false, annonce « Données de sommeil non disponibles » et ne "
    "reprends JAMAIS le sommeil du jour précédent à la place.\n"
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


def _shorten_notification(text: str, max_lines: int = 4, limit: int = 300) -> str:
    """Crée une notification ultra-courte pour montre/téléphone (max 4 lignes)."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    # Garder seulement les lignes qui contiennent des infos utiles (chiffres, verdict)
    filtered = [l for l in lines if any(c.isdigit() for c in l) or any(w in l.lower() for w in ["verdict", "coach", "charge", "récup", "effort", "distance", "durée", "fc", "hrv"])]
    if not filtered:
        filtered = lines
    short = "\n".join(filtered[:max_lines])
    return short if len(short) <= limit else short[: limit - 1] + "…"


def _feed_sections(text: str) -> str:
    """Sections Markdown rendues lisibles en texte simple (assistant IA)."""
    lines = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        lines.append(f"— {stripped[3:].strip()} —" if stripped.startswith("## ") else line)
    return "\n".join(lines).strip()


class SportAnalysisService:
    """Génère et stocke les analyses sportives automatiques d'un utilisateur."""

    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user
        self.sport = SportService(db, current_user)

    # ------------------------------------------------------------------ #
    # Analyses
    # ------------------------------------------------------------------ #

    async def analyze_morning(self, notify: bool = True) -> tuple[bool, SportAnalysis | None]:
        """(nouvelle_analyse, analyse) — idempotente par jour et par athlète."""
        return await self._analyze_daily("morning", _MORNING_INSTRUCTION, self._morning_context, notify)

    async def morning_sleep_available(self) -> bool:
        """Vrai si la nuit dernière figure déjà dans les données du jour.

        Garmin date le sommeil par le jour de réveil : la nuit écoulée est
        rangée sous aujourd'hui une fois synchronisée. Tant qu'elle manque,
        l'analyse du matin patiente (sinon elle décrirait la nuit d'avant).

        Garmin renvoie aussi un squelette ``sleep`` vide pour le jour en
        cours : la présence de la clé ne suffit pas, il faut une durée.
        """
        athlete = await self.sport.get_or_create_athlete()
        health_json = await self.db.scalar(
            select(SportHealthDaily.health_json).where(
                SportHealthDaily.athlete_id == athlete.id,
                SportHealthDaily.day == self._local_today(),
            )
        )
        if not isinstance(health_json, dict):
            return False
        sleep = health_json.get("sleep")
        if not isinstance(sleep, dict) or not sleep:
            return False
        dto = sleep.get("dailySleepDTO")
        if not isinstance(dto, dict):
            dto = {}
        total = (
            sleep.get("sleepTimeSeconds")
            or sleep.get("totalSleepSeconds")
            or dto.get("sleepTimeSeconds")
            or dto.get("totalSleepSeconds")
        )
        return total is not None

    async def analyze_evening(self, notify: bool = True) -> tuple[bool, SportAnalysis | None]:
        return await self._analyze_daily("evening", _EVENING_INSTRUCTION, self._evening_context, notify)

    async def _analyze_daily(
        self,
        analysis_type: str,
        instruction: str,
        context_builder,
        notify: bool = True,
    ) -> tuple[bool, SportAnalysis | None]:
        athlete = await self.sport.get_or_create_athlete()
        day = self._local_today()
        dedupe_key = f"{analysis_type}:{day.isoformat()}"
        existing = await self._find(athlete, dedupe_key)
        if existing is not None:
            if notify:
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
            notify=notify,
        )

    async def analyze_activity(self, activity_id: int, notify: bool = True) -> tuple[bool, SportAnalysis | None]:
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
            if notify:
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
            notify=notify,
        )

    async def list_activities_due(self, now: datetime | None = None) -> list[SportActivity]:
        """Activités Garmin éligibles à une analyse automatique.

        Une activité n'est prise en compte qu'une seule fois ; elle doit être
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
        return [
            activity
            for activity in activities
            if self._ends_at(activity) <= _naive_utc(now)
        ]

    async def analyze_recent_activities(self, now: datetime | None = None) -> int:
        """Analyse les activités Garmin récemment synchronisées (après délai)."""
        now = now or datetime.now(timezone.utc)
        activities = await self.list_activities_due(now)
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
                temperature=0.3,
                max_tokens=2000,
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
        # Notification : 4 lignes max, format compact
        raw_notification = str(payload.get("summary") or payload["content"])
        payload.setdefault("notification", _shorten_notification(raw_notification))
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
        notify: bool = True,
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
            # Sans notification, la cible est d'emblée considérée comme traitée :
            # un passage ultérieur du cycle ne doit pas la notifier à retardement.
            notification_sent=not notify,
        )
        self.db.add(analysis)
        try:
            await self.db.flush()
        except IntegrityError:
            # Course avec un autre cycle : l'analyse existe déjà, rien à faire.
            await self.db.rollback()
            return False, await self._find(athlete, dedupe_key)
        await self.db.commit()
        if notify:
            await self._notify(athlete, analysis, analysis_type)
        await self._publish(athlete, analysis)
        return True, analysis

    async def _publish(self, athlete: SportAthlete, analysis: SportAnalysis) -> None:
        """Publie l'analyse dans la conversation « Coach & Analyses » de l'assistant."""
        if not athlete.user_id:
            return
        if self.current_user.id != athlete.user_id:
            return
        title = (analysis.title or "").strip()
        parts = [
            part
            for part in ((analysis.summary or "").strip(), _feed_sections(analysis.content or ""))
            if part
        ]
        if not parts and not title:
            return
        text = f"{title}\n\n" + "\n\n".join(parts) if title and parts else (title or "\n\n".join(parts))
        await coach_feed.publish(self.db, self.current_user, content=text, model="coach")

    async def _notify(self, athlete: SportAthlete, analysis: SportAnalysis, analysis_type: str) -> None:
        if analysis.notification_sent or not athlete.user_id:
            return
        title = f"{_EMOJI.get(analysis_type, '')} {_NOTIFICATION_TITLES.get(analysis_type, 'Analyse Sport')}".strip()
        # Construire un message plus détaillé
        message_parts = []
        if analysis.summary:
            message_parts.append(analysis.summary)
        if analysis.content and len(analysis.content) > len(analysis.summary or ""):
            # Ajouter le contenu s'il apporte plus que le résumé
            content_preview = analysis.content[:300]
            if len(analysis.content) > 300:
                content_preview += "..."
            message_parts.append(content_preview)
        message = "\n\n".join(message_parts) if message_parts else analysis.title
        try:
            await NotificationService(self.db).send(
                user_id=athlete.user_id,
                title=title,
                message=message,
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
        "agent_events": 0,
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
        agent_on = bool(settings.SPORT_AGENT_ENABLED)
        day_key = SportAnalysisService._local_today().isoformat()
        if morning_due and await _morning_ready(service, morning_deadline, local_time):
            agent_turn = agent_on and await _agent_due(db, athlete, "morning")
            stats["errors"] += await _dispatch_analysis(
                db,
                user,
                "morning",
                stats,
                "morning",
                service.analyze_morning,
                agent_turn,
                ensure_ready=lambda: _analysis_exists(db, athlete, f"morning:{day_key}"),
            )
        if evening_due:
            agent_turn = agent_on and await _agent_due(db, athlete, "evening")
            stats["errors"] += await _dispatch_analysis(
                db,
                user,
                "evening",
                stats,
                "evening",
                service.analyze_evening,
                agent_turn,
                ensure_ready=lambda: _analysis_exists(db, athlete, f"evening:{day_key}"),
            )
        if activity_due:
            payload: dict[str, Any] | None = None
            agent_turn = False
            if agent_on:
                pending = await _pending_activity_ids(db, athlete, service, now)
                agent_turn = bool(pending) and not await _agent_cooldown(db, athlete, "activity", now)
                if agent_turn:
                    payload = {"activity_ids": pending}
            stats["errors"] += await _dispatch_analysis(
                db,
                user,
                "activity",
                stats,
                "activities",
                lambda: service.analyze_recent_activities(now),
                agent_turn,
                payload,
                ensure_ready=lambda: _activities_analyzed(db, athlete, service, now),
            )
        if agent_on:
            # Événement métier : une recommandation d'entraînement échue est
            # signalée une seule fois (marquage dans result_json), puis
            # l'agent décide quoi en faire.
            try:
                from app.services.sport_agent.events import (
                    collect_missed_training_events,
                    emit_agent_event,
                )

                missed = await collect_missed_training_events(db, athlete.id, now)
                for event_trigger, event_payload in missed:
                    outcome = await emit_agent_event(db, user, athlete.id, event_trigger, event_payload)
                    stats["agent_events"] += 1
                    logger.info(
                        "[SPORT-ANALYSIS] event=agent_event trigger=%s status=%s",
                        event_trigger,
                        (outcome or {}).get("status"),
                    )
                if missed:
                    await db.commit()
            except Exception:
                logger.exception(
                    "[SPORT-ANALYSIS] Échec événement Agent Sport (user %s)", user.id
                )
                try:
                    await db.rollback()
                except Exception:
                    logger.exception("[SPORT-ANALYSIS] rollback événement impossible")
    return stats


async def _dispatch_analysis(
    db: AsyncSession,
    user: User,
    trigger: str,
    stats: dict[str, Any],
    stat_key: str,
    legacy_factory,
    agent_turn: bool,
    payload: dict[str, Any] | None = None,
    ensure_ready=None,
) -> int:
    """Réveil de l'Agent Sport, avec repli obligatoire sur le job historique.

    Le job historique n'est court-circuité que si l'agent a effectivement
    traité le déclencheur (même si aucune nouvelle analyse n'a été créée,
    car elle existait déjà) ET que l'analyse attendue est bien en base
    (``ensure_ready``). Dans tous les autres cas (drapeau éteint, agent en
    échec, en repli, sans résultat ou analyse manquante) il s'exécute comme
    par le passé : le modèle ne peut pas décider de supprimer une analyse.
    """
    if agent_turn:
        outcome: dict[str, Any] | None = None
        try:
            # Import tardif : sport_agent dépend de ce module (analyse du matin/soir).
            from app.services.sport_agent import run_agent_trigger

            outcome = await run_agent_trigger(db, user, trigger, payload=payload)
        except Exception:
            logger.exception("[SPORT-ANALYSIS] Échec Agent Sport %s (user %s)", trigger, user.id)
        created = int((outcome or {}).get("created_analyses") or 0)
        status = (outcome or {}).get("status")
        # L'agent a traité le déclencheur (même si 0 analyse créée car déjà existante) :
        # on ne doit PAS tomber dans le fallback legacy, sauf si l'analyse attendue
        # n'est pas en base.
        if status in ("completed", "budget_exhausted"):
            ready = True
            if ensure_ready is not None:
                try:
                    ready = bool(await ensure_ready())
                except Exception:
                    logger.exception(
                        "[SPORT-ANALYSIS] Vérification analyse %s impossible", trigger
                    )
                    ready = False
            if ready:
                stats[stat_key] += created
                return 0
            logger.warning(
                "[SPORT-ANALYSIS] Agent %s terminé sans analyse en base → repli historique (user %s)",
                trigger,
                user.id,
            )
        else:
            logger.warning(
                "[SPORT-ANALYSIS] Agent %s status=%s (created=%d) → repli historique (user %s)",
                trigger,
                status,
                created,
                user.id,
            )
    try:
        result = await legacy_factory()
    except Exception:
        logger.exception("[SPORT-ANALYSIS] Échec analyse %s", trigger)
        return 1
    created = result[0] if isinstance(result, tuple) else result
    if isinstance(created, bool):
        created = 1 if created else 0
    stats[stat_key] += int(created or 0)
    return 0


async def _analysis_exists(db: AsyncSession, athlete: SportAthlete, dedupe_key: str) -> bool:
    existing = await db.scalar(
        select(SportAnalysis.id).where(
            SportAnalysis.athlete_id == athlete.id,
            SportAnalysis.dedupe_key == dedupe_key,
        )
    )
    return existing is not None


async def _agent_due(db: AsyncSession, athlete: SportAthlete, kind: str) -> bool:
    """L'agent planifié (matin/soir) ne se réveille que s'il reste une analyse
    à produire et qu'il n'a pas déjà tourné pour ce déclencheur."""
    if await _agent_cooldown(db, athlete, kind, datetime.now(timezone.utc)):
        return False
    dedupe_key = f"{kind}:{SportAnalysisService._local_today().isoformat()}"
    return not await _analysis_exists(db, athlete, dedupe_key)


async def _agent_cooldown(db: AsyncSession, athlete: SportAthlete, trigger: str, now: datetime) -> bool:
    """Un même déclencheur ne réveille pas l'agent plus d'une fois par
    ``AGENT_TRIGGER_COOLDOWN_MINUTES`` : la boucle tourne toutes les minutes.

    L'implémentation est partagée avec ``sport_agent.triggers`` afin que le
    cycle planifié et les événements appliquent exactement la même règle."""
    from app.services.sport_agent.triggers import agent_woken_recently

    return await agent_woken_recently(db, athlete.id, trigger, now)


async def _pending_activity_ids(
    db: AsyncSession, athlete: SportAthlete, service: SportAnalysisService, now: datetime
) -> list[int]:
    """Activités dues et pas encore analysées (idempotence identique au job)."""
    due = await service.list_activities_due(now)
    if not due:
        return []
    ids = [activity.id for activity in due]
    analyzed = set(
        (
            await db.execute(
                select(SportAnalysis.activity_id).where(
                    SportAnalysis.athlete_id == athlete.id,
                    SportAnalysis.analysis_type == "activity",
                    SportAnalysis.activity_id.in_(ids),
                )
            )
        ).scalars()
    )
    return [activity_id for activity_id in ids if activity_id not in analyzed]


async def _activities_analyzed(
    db: AsyncSession, athlete: SportAthlete, service: SportAnalysisService, now: datetime
) -> bool:
    """Vrai si toutes les activités dues ont bien été analysées (garde du repli)."""
    return not await _pending_activity_ids(db, athlete, service, now)


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
