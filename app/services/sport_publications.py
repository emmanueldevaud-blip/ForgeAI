"""Service de generation de publications Instagram a partir des activites sportives.

Reutilise SportService (lecture seule), l'AI Gateway et NotificationService.
Ne copie aucune donnee d'activite : une publication reference l'activite.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.photo import Photo
from app.models.sport import SportActivity, SportAthlete, SportPublication, EditorialCalendarEntry, CommunityManagerStrategy
from app.models.user import User
from app.schemas.sport import SportPublicationGenerateRequest, PublicationGenerateFromCalendarRequest
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.notification import NotificationService
from app.services.sport import SportService

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads/sport")
PUBLICATIONS_SUBDIR = "publications"

STYLE_LABELS = {
    "humor": "Humour et autoderision",
    "stats": "Statistiques et performance",
    "motivation": "Motivation et depassement",
    "inspiring": "Inspirant et emotionnel",
    "story": "Recit de sortie",
    "ultra": "Esprit ultra-trail",
    "short": "Court et percutant",
    "custom": "Personnalise",
    "mix": "Mix de styles",
}

STYLE_INSTRUCTIONS = {
    "humor": "Ton humoristique et autoderisif : difficultes, jambes lourdes, montees, choix absurdes du traileur. Leger, jamais moqueur.",
    "stats": "Ton factuel et performance : chiffres, distance, D+, duree, allure, FC, progression. Precis, sobre.",
    "motivation": "Ton motivant et depassement : effort, mental, perseverance, objectifs. Energique, encourageant.",
    "inspiring": "Ton inspirant et emotionnel : paysages, plaisir, liberte, sensations. Poetique, sensible.",
    "story": "Ton recit : petite histoire de la seance, debut, milieu, fin. Narratif.",
    "ultra": "Ton ultra-trail : fatigue, longues distances, gestion de l'effort, mental. Brut, authentique.",
    "short": "Ton court et percutant : publication courte, une phrase accrocheuse. Concis.",
    "custom": "Ton defini par l'utilisateur dans ses consignes personnalisees.",
    "mix": "Ton mixte : combiner plusieurs tons choisis (ex. stats + humour).",
}

VALID_STYLES = set(STYLE_LABELS.keys())

SYSTEM_PROMPT = """
# RÔLE : EXPERT INSTAGRAM – TRAIL RUNNING & CROISSANCE D'AUDIENCE

Tu es un expert en community management, marketing Instagram, storytelling sportif et création de contenu spécialisé dans le trail running et l'ultra-trail.

Ta mission est de transformer chaque sortie Garmin en une publication Instagram à fort potentiel de visibilité, de partage et de recrutement de nouveaux abonnés.

Ton objectif prioritaire est de faire grandir le compte Instagram du coureur de manière organique et durable.

## 1. IDENTITÉ DU COMPTE

Le compte raconte la vie d'un traileur passionné qui :
- Pratique le trail et l'ultra-trail.
- Réalise des sorties longues et des défis sportifs.
- Accumule les kilomètres et le dénivelé.
- Connaît les difficultés de l'entraînement, la fatigue et les douleurs.
- Cherche constamment à progresser.
- Aime partager ses expériences sans se prendre trop au sérieux.

La personnalité doit être humaine, authentique, reconnaissable et attachante.

Ne jamais donner l'impression d'un compte publicitaire ou d'un robot qui récite des statistiques.

## 2. OBJECTIFS DE CHAQUE PUBLICATION

Chaque publication doit chercher à obtenir, dans cet ordre :
1. Un maximum de visibilité auprès des non-abonnés.
2. Un maximum de partages en messages privés.
3. Des commentaires et des discussions.
4. Des abonnements supplémentaires.
5. Une communauté fidèle de passionnés de trail.

Ne cherche pas uniquement à obtenir des likes.

Crée du contenu que les traileurs auront envie d'envoyer à leurs partenaires d'entraînement.

## 3. EXPLOITER LES DONNÉES GARMIN

Analyse les données disponibles :
- Distance.
- Dénivelé positif et négatif.
- Durée.
- Allure moyenne.
- Fréquence cardiaque.
- Calories.
- Vitesse.
- Records éventuels.
- Évolution par rapport aux sorties précédentes.
- Type de séance.
- Conditions et contexte disponibles.

Ne transforme jamais une statistique banale en exploit extraordinaire.

Identifie systématiquement le détail le plus intéressant, surprenant, drôle ou impressionnant de la sortie.

Les chiffres doivent servir l'histoire, pas remplacer l'histoire.

N'invente aucune donnée et signale toute information manquante.

## 4. TON DE PUBLICATION

Le ton est sélectionnable par l'utilisateur :

- HUMOUR : autodérision, second degré, situations absurdes, fatigue, souffrance du traileur.
- STATISTIQUES : chiffres marquants, performances, comparaisons, analyse sportive.
- MOTIVATION : dépassement de soi, persévérance, progression, objectifs.
- PROVOCATION : phrases percutantes, humour piquant, petites provocations entre traileurs.
- STORYTELLING : raconter la sortie comme une petite aventure avec un début, un moment difficile et une conclusion.
- ULTRA-TRAIL : esprit de l'ultra, kilomètres, dénivelé, gestion de l'effort et mental.
- MIXTE : mélange intelligent d'humour, de statistiques et d'émotion.

Respecte impérativement le ton sélectionné.

## 5. ACCROCHE : LES 3 PREMIÈRES SECONDES

C'est l'élément le plus important.

Commence toujours par une phrase courte, originale et percutante.

Exemples de styles :
- « J'avais prévu une petite sortie tranquille. Garmin n'était pas du même avis. »
- « 25 km pour réfléchir à mes choix de vie. »
- « Le dénivelé était gratuit. La souffrance aussi. »
- « Mon cardio va bien. Mon ego un peu moins. »
- « Certains collectionnent les timbres. Moi, les kilomètres. »

Ces exemples sont des inspirations. Ne les recycle pas systématiquement.

Crée une accroche spécifique à chaque activité.

Évite les introductions classiques comme « Belle sortie aujourd'hui » ou « Encore une bonne séance ».

## 6. CONSTRUCTION DE LA PUBLICATION

Structure chaque publication de cette manière :

A. ACCROCHE
Une phrase qui donne envie de lire la suite.

B. HISTOIRE
Raconte la sortie avec naturel, humour ou émotion selon le ton choisi.

C. CHIFFRES MARQUANTS
Intègre uniquement les statistiques les plus intéressantes.

D. CHUTE
Termine avec une phrase mémorable, drôle, motivante ou surprenante.

E. APPEL À L'INTERACTION
Pose une question simple qui donne envie de répondre.

Exemples :
- « Vous aussi, vous trouvez toujours une bonne excuse pour rajouter 5 km ? »
- « Team montée ou team descente ? »
- « C'est quoi votre dernière sortie complètement déraisonnable ? »

F. HASHTAGS
Utilise quelques hashtags très ciblés et pertinents. Évite les listes interminables de hashtags génériques.

## 7. STRATÉGIE DE FORMATS

Choisis le format le plus pertinent selon les données et les médias réellement disponibles.

- REEL : privilégier les moments spectaculaires, les défis, les anecdotes et les histoires avec un fort potentiel de partage. Fournir un scénario, une accroche à afficher dès le début, les séquences à utiliser et les textes à incruster.
- CARROUSEL : privilégier les bilans, les comparaisons, les statistiques et les histoires en plusieurs étapes. Prévoir une première diapositive qui donne envie de faire défiler.
- PHOTO : privilégier une image forte avec une légende qui raconte quelque chose.
- STORY : privilégier les réactions rapides, les coulisses et les interactions avec les abonnés.

Ne prétends jamais disposer de photos ou de vidéos si elles ne sont pas fournies.

Ne recommande pas systématiquement un Reel. Choisis le format qui sert le mieux le contenu.

## 8. RÈGLES DE QUALITÉ

- Chaque publication doit être originale.
- Bannir les textes génériques.
- Éviter les répétitions d'accroches.
- Ne pas surcharger les publications d'emojis.
- Éviter les textes trop longs et artificiels.
- Privilégier un langage naturel, vivant et spontané.
- Ne pas inventer de performances ou d'exploits.
- Ne jamais utiliser de techniques artificielles pour générer de faux commentaires ou de faux abonnés.
- Ne pas mendier des likes.
- Ne pas utiliser de hashtags sans rapport avec la publication.

## 9. OPTIMISATION ET APPRENTISSAGE

Lorsque les statistiques Instagram sont disponibles, analyse les publications précédentes :
- Portée totale.
- Part des non-abonnés.
- Nombre de partages.
- Nombre de commentaires.
- Nombre de likes.
- Nombre de sauvegardes.
- Nouveaux abonnés générés.
- Temps de visionnage des Reels.

Identifie les sujets, accroches, formats et tons qui fonctionnent le mieux.

Adapte progressivement les prochaines publications aux résultats réels.

Ne reproduis pas systématiquement une publication qui a bien fonctionné : cherche à comprendre pourquoi elle a fonctionné et à renouveler l'idée.

## 10. FORMAT DE SORTIE OBLIGATOIRE

Pour chaque activité Garmin, retourne :
1. ANGLE ÉDITORIAL : l'idée retenue pour cette publication.
2. FORMAT CONSEILLÉ : Reel, carrousel, photo ou story.
3. ACCROCHE : la phrase d'ouverture.
4. PUBLICATION INSTAGRAM : texte complet prêt à publier.
5. HASHTAGS : sélection ciblée.
6. IDÉE VISUELLE : description du visuel ou des séquences nécessaires.
7. OBJECTIF : visibilité, partage, commentaires ou abonnements.

Si plusieurs angles sont particulièrement intéressants, propose jusqu'à trois concepts et sélectionne le meilleur.

## 11. VALIDATION OBLIGATOIRE

La publication ne doit jamais être envoyée automatiquement sur Instagram.

Présente le résultat à l'utilisateur pour validation.

L'utilisateur doit pouvoir modifier le texte, choisir un autre ton, demander une autre accroche ou changer le format avant toute publication.

## OBJECTIF FINAL

Ne te contente pas de raconter une sortie Garmin.

Transforme chaque sortie en contenu original qui donne envie de rire, de réagir, de partager et de suivre les prochaines aventures.

Chaque publication doit contribuer à construire une identité Instagram forte dans l'univers du trail running et de l'ultra-trail.

## STRATÉGIE ÉDITORIALE ET CROISSANCE INSTAGRAM TRAIL

Tu dois appliquer une stratégie éditoriale permanente à toutes les publications Instagram générées.

## POSITIONNEMENT

Construire un compte Instagram reconnu dans l'univers du trail running et de l'ultra-trail.

Le personnage est un traileur expérimenté, passionné, qui réalise de longues sorties, accumule du dénivelé et relève des défis sportifs.

Sa personnalité repose sur un mélange de :
- Humour et autodérision.
- Performances sportives.
- Authenticité.
- Dépassement de soi.
- Passion du trail et de l'ultra-trail.

Le compte doit être attachant, identifiable et accessible aux traileurs amateurs comme aux passionnés d'ultra.

## OBJECTIF PRIORITAIRE

Développer une audience organique et engagée.

Privilégier les contenus qui :
1. Attirent des personnes qui ne connaissent pas encore le compte.
2. Suscitent des partages.
3. Génèrent des conversations.
4. Convertissent les visiteurs en abonnés.
5. Fidélisent la communauté.

## RÉPARTITION ÉDITORIALE CIBLE

- 30 % humour et galères du traileur.
- 25 % performances et défis.
- 20 % aventures et paysages.
- 15 % coulisses de l'ultra-trail.
- 10 % communauté et interactions.

Adapter ces proportions selon les sorties et les résultats observés.

## SIGNATURE DU COMPTE

Chaque contenu doit conserver une personnalité reconnaissable.

Privilégier :
- Des accroches originales.
- Des phrases courtes et mémorables.
- Des comparaisons humoristiques.
- Des situations auxquelles les traileurs s'identifient.
- Des statistiques réellement intéressantes.
- Des histoires authentiques.

Éviter les publications qui ressemblent à un simple compte rendu Garmin.

## CHOIX DU CONTENU

Ne pas chercher systématiquement à publier chaque activité.

Évaluer l'intérêt éditorial de chaque sortie.

Une sortie banale peut devenir une bonne publication si elle contient une anecdote, une situation drôle ou un enseignement intéressant.

Une grosse performance peut devenir une publication forte grâce à son histoire, son contexte et ses chiffres.

Si aucune idée intéressante n'émerge, privilégier une publication différée ou ne rien proposer.

## STRATÉGIE DE CROISSANCE

Pour chaque contenu, déterminer son objectif principal :
- Découverte.
- Partage.
- Interaction.
- Fidélisation.

Ne pas chercher à remplir tous les objectifs dans une seule publication.

Favoriser les formats adaptés :
- Reels pour toucher de nouveaux publics.
- Carrousels pour raconter, expliquer et faire enregistrer.
- Photos pour les moments forts.
- Stories pour entretenir la relation avec la communauté.

## APPRENTISSAGE PAR LES RÉSULTATS

Exploiter les statistiques Instagram lorsqu'elles sont accessibles.

Analyser les résultats par format, thème, accroche et ton.

Ne pas considérer les likes comme le seul indicateur de réussite.

Mesurer notamment :
- Portée auprès des non-abonnés.
- Partages.
- Enregistrements.
- Commentaires.
- Visites du profil.
- Nouveaux abonnés.
- Temps de visionnage des Reels.

Comparer les résultats à l'historique du compte et à la performance habituelle de chaque format.

Faire évoluer les recommandations à partir des résultats constatés.

Ne jamais prétendre qu'une publication est virale ou performante sans données pour le démontrer.

## RÈGLE FONDAMENTALE

Chaque publication doit donner au lecteur une raison de s'arrêter, de sourire, de réagir ou de partager.

L'objectif n'est pas de publier plus.

L'objectif est de devenir un compte trail que les gens ont envie de retrouver."""

def _athlete_settings(athlete: SportAthlete) -> dict[str, Any]:
    meta = athlete.metadata_json if isinstance(athlete.metadata_json, dict) else {}
    cfg = meta.get("publications")
    if not isinstance(cfg, dict):
        cfg = {"notifications_enabled": True, "last_styles": [], "last_custom_instructions": None}
        meta["publications"] = cfg
        athlete.metadata_json = meta
        flag_modified(athlete, "metadata_json")
    cfg.setdefault("notifications_enabled", True)
    cfg.setdefault("last_styles", [])
    cfg.setdefault("last_custom_instructions", None)
    cfg.setdefault("last_notified_activity_id", None)
    return cfg


def _fmt_stat(value: Any, suffix: str = "") -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, float):
            if value == int(value) and abs(value) < 1e9:
                value = int(value)
            else:
                value = round(value, 2)
    except (TypeError, ValueError):
        pass
    return f"{value}{suffix}"


def _activity_stats(activity: SportActivity) -> dict[str, Any]:
    return {
        "sport_type": activity.sport_type,
        "activity_name": activity.activity_name,
        "started_at": activity.started_at.isoformat() if activity.started_at else None,
        "duration_seconds": activity.duration_seconds,
        "distance_m": activity.distance_m,
        "elevation_gain_m": activity.elevation_gain_m,
        "elevation_loss_m": activity.elevation_loss_m,
        "avg_speed_m_s": activity.avg_speed_m_s,
        "avg_pace_sec_km": activity.avg_pace_sec_km,
        "avg_heart_rate": activity.avg_heart_rate,
        "max_heart_rate": activity.max_heart_rate,
        "avg_cadence": activity.avg_cadence,
        "avg_power_w": activity.avg_power_w,
        "calories": activity.calories,
        "temperature_c": activity.temperature_c,
        "source_type": activity.source_type,
    }


def _previous_publications_context(db_publications: list[SportPublication]) -> str:
    if not db_publications:
        return "Aucune publication precedente."
    lines = []
    for p in db_publications[:8]:
        txt = (p.content or "").strip()
        if txt:
            lines.append(f"- {txt[:240]}")
    return "\n".join(lines) if lines else "Aucune publication precedente."


class SportPublicationService:
    def __init__(self, db: AsyncSession, current_user: User):
        self.db = db
        self.current_user = current_user

    async def get_or_create_athlete(self) -> SportAthlete:
        return await SportService(self.db, self.current_user).get_or_create_athlete()

    async def get_activity(self, activity_id: int) -> Optional[SportActivity]:
        athlete = await self.get_or_create_athlete()
        res = await self.db.execute(
            select(SportActivity).where(
                SportActivity.id == activity_id, SportActivity.athlete_id == athlete.id
            )
        )
        return res.scalar_one_or_none()

    async def get_publication(self, publication_id: int) -> Optional[SportPublication]:
        athlete = await self.get_or_create_athlete()
        res = await self.db.execute(
            select(SportPublication).where(
                SportPublication.id == publication_id, SportPublication.athlete_id == athlete.id
            )
        )
        return res.scalar_one_or_none()

    async def get_for_activity(self, activity_id: int) -> Optional[SportPublication]:
        athlete = await self.get_or_create_athlete()
        res = await self.db.execute(
            select(SportPublication).where(
                SportPublication.activity_id == activity_id,
                SportPublication.athlete_id == athlete.id,
            )
        )
        return res.scalar_one_or_none()

    async def list_publications(
        self, status: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        athlete = await self.get_or_create_athlete()
        query = select(SportPublication).where(SportPublication.athlete_id == athlete.id)
        if status:
            query = query.where(SportPublication.status == status)
        total = (
            await self.db.execute(
                select(func.count(SportPublication.id)).where(SportPublication.athlete_id == athlete.id)
                if not status
                else select(func.count(SportPublication.id)).where(
                    SportPublication.athlete_id == athlete.id, SportPublication.status == status
                )
            )
        ).scalar() or 0
        query = query.order_by(SportPublication.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        rows = (await self.db.execute(query)).scalars().all()
        # attache l'activite
        for pub in rows:
            if pub.activity is None:
                ares = await self.db.execute(select(SportActivity).where(SportActivity.id == pub.activity_id))
                pub.activity = ares.scalar_one_or_none()
        return {
            "items": list(rows),
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, -(-total // page_size)),
        }

    async def recent_activities_for_publication(self, limit: int = 20) -> list[SportActivity]:
        athlete = await self.get_or_create_athlete()
        res = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id)
            .order_by(SportActivity.started_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    def _validate_styles(self, styles: list[str]) -> list[str]:
        cleaned = []
        for s in styles or []:
            s = (s or "").strip().lower()
            if s in VALID_STYLES and s not in cleaned:
                cleaned.append(s)
        return cleaned

    async def generate(
        self, activity_id: int, data: SportPublicationGenerateRequest
    ) -> SportPublication:
        activity = await self.get_activity(activity_id)
        if activity is None:
            raise ValueError("Activite introuvable")
        styles = self._validate_styles(data.styles)
        if not styles:
            styles = ["stats"]
        if "custom" in styles and not (data.custom_instructions or "").strip():
            styles = [s for s in styles if s != "custom"] or ["stats"]
        custom = (data.custom_instructions or "").strip() or None

        pub = await self.get_for_activity(activity_id)
        if pub is None:
            athlete = await self.get_or_create_athlete()
            pub = SportPublication(
                athlete_id=athlete.id,
                activity_id=activity_id,
                status="draft",
            )
            self.db.add(pub)
            await self.db.flush()

        # historique des publications precedentes (anti-repetition)
        prev_rows = (
            await self.db.execute(
                select(SportPublication).where(
                    SportPublication.athlete_id == pub.athlete_id,
                    SportPublication.id != pub.id,
                ).order_by(SportPublication.created_at.desc()).limit(8)
            )
        ).scalars().all()
        prev_ctx = _previous_publications_context(list(prev_rows))

        # tons effectifs
        effective_styles = list(styles)
        if "mix" in effective_styles:
            effective_styles = [s for s in effective_styles if s != "mix"]
            if not effective_styles:
                effective_styles = ["stats", "humor"]

        style_lines = "\n".join(
            f"- {STYLE_LABELS.get(s, s)} : {STYLE_INSTRUCTIONS.get(s, '')}" for s in effective_styles
        )
        if custom:
            style_lines += f"\n- Consignes personnalisees de l'utilisateur : {custom}"

        mix_note = ""
        if len(effective_styles) > 1:
            mix_note = " Mode MIX : combiner les tons selectionnes dans une meme proposition quand c'est pertinent."

        prompt = (
            f"Activite sportive (donnees reelles uniquement) :\n"
            f"{json.dumps(_activity_stats(activity), ensure_ascii=False, default=str)}\n\n"
            f"Tons demandes :\n{style_lines}{mix_note}\n\n"
            f"Historique des publications precedentes (a eviter) :\n{prev_ctx}\n\n"
            f"Genere 3 concepts de publication (propositions) distincts et adaptes a ces tons. "
            f"Pour chaque concept retourne un objet avec : angle, format (Reel/carrousel/photo/story), "
            f"accroche, publication, hashtags, idee_visuelle, objectif. "
            f"Si plusieurs angles sont interessants, propose jusqu'a trois concepts et selectionne le meilleur. "
            f"Reponds uniquement en JSON avec la cle 'proposals'."
        )

        started = datetime.now(timezone.utc)
        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=1800,
            )
        except AIGatewayError as exc:
            logger.warning("[SPORT-PUB] IA indisponible : %s", exc)
            pub.styles = styles
            pub.custom_instructions = custom
            pub.proposals = []
            pub.provider = None
            pub.model = None
            pub.generated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(pub)
            raise

        text = (response.text or "").strip()
        payload = None
        try:
            # parse json
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

        proposals_raw = []
        if isinstance(payload, dict) and isinstance(payload.get("proposals"), list):
            for p in payload["proposals"][:3]:
                if not isinstance(p, dict):
                    continue
                content = str(p.get("content") or "").strip()
                if not content:
                    continue
                proposals_raw.append({
                    "title": (str(p.get("title")).strip() if p.get("title") is not None else None),
                    "content": content,
                    "hashtags": (str(p.get("hashtags")).strip() if p.get("hashtags") is not None else None),
                })

        if not proposals_raw:
            # repli : une seule proposition avec le texte brut
            proposals_raw = [{"title": "Publication", "content": text, "hashtags": None}]

        # complete a 3 si besoin
        while len(proposals_raw) < 3:
            proposals_raw.append({"title": None, "content": "", "hashtags": None})
        proposals_raw = proposals_raw[:3]

        pub.styles = styles
        pub.custom_instructions = custom
        pub.proposals = proposals_raw
        pub.selected_proposal = 0
        pub.title = proposals_raw[0].get("title")
        pub.content = proposals_raw[0].get("content")
        pub.hashtags = proposals_raw[0].get("hashtags")
        pub.provider = getattr(response, "provider_used", None)
        pub.model = getattr(response, "model_used", None)
        pub.generated_at = datetime.now(timezone.utc)
        pub.status = "draft"
        await self.db.commit()
        await self.db.refresh(pub)
        # attache activite
        pub.activity = activity
        return pub

    async def generate_from_calendar_entry(
        self, calendar_entry_id: int, data: Any
    ) -> Optional[SportPublication]:
        """Génère une publication Instagram à partir d'une entrée de calendrier validée (V2)."""
        # Vérifier que l'entrée appartient à l'utilisateur
        athlete = await self.get_or_create_athlete()
        strategy_result = await self.db.execute(
            select(CommunityManagerStrategy).where(
                CommunityManagerStrategy.athlete_id == athlete.id
            )
        )
        strategy = strategy_result.scalar_one_or_none()
        if not strategy:
            raise ValueError("Stratégie éditoriale non configurée")

        entry_result = await self.db.execute(
            select(EditorialCalendarEntry).where(
                EditorialCalendarEntry.id == calendar_entry_id,
                EditorialCalendarEntry.strategy_id == strategy.id,
            )
        )
        entry = entry_result.scalar_one_or_none()
        if not entry:
            raise ValueError("Entrée de calendrier introuvable")

        if entry.status != "planifié":
            raise ValueError("L'entrée doit être validée (statut 'planifié') pour créer une publication")

        # Vérifier s'il existe déjà une publication pour cette entrée
        existing_pub_result = await self.db.execute(
            select(SportPublication).where(
                SportPublication.calendar_entry_id == calendar_entry_id,
                SportPublication.athlete_id == athlete.id,
            )
        )
        existing_pub = existing_pub_result.scalar_one_or_none()

        styles = data.styles if hasattr(data, "styles") and data.styles else []
        custom = data.custom_instructions if hasattr(data, "custom_instructions") and data.custom_instructions else None
        tone = data.tone if hasattr(data, "tone") and data.tone else None
        visual_type = data.visual_type if hasattr(data, "visual_type") and data.visual_type else "photo"
        photo_id = data.photo_id if hasattr(data, "photo_id") and data.photo_id else None

        # Si pas de styles fournis, utiliser ceux de la stratégie ou défaut
        if not styles:
            styles = ["stats"]

        # Récupérer les activités récentes pour le contexte
        recent_activities = []
        activities_result = await self.db.execute(
            select(SportActivity)
            .where(SportActivity.athlete_id == athlete.id)
            .order_by(SportActivity.started_at.desc())
            .limit(10)
        )
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

        # Construire le prompt pour la génération V2
        prompt = self._build_v2_generation_prompt(
            entry=entry,
            strategy=strategy,
            recent_activities=recent_activities,
            styles=styles,
            custom_instructions=custom,
            tone=tone,
            visual_type=visual_type,
        )

        # Créer ou récupérer la publication
        if existing_pub:
            pub = existing_pub
        else:
            pub = SportPublication(
                athlete_id=athlete.id,
                calendar_entry_id=calendar_entry_id,
                status="draft",
                created_from="calendar",
            )
            self.db.add(pub)
            await self.db.flush()

        # Historique pour éviter répétition
        prev_rows = (
            await self.db.execute(
                select(SportPublication).where(
                    SportPublication.athlete_id == pub.athlete_id,
                    SportPublication.id != pub.id,
                ).order_by(SportPublication.created_at.desc()).limit(8)
            )
        ).scalars().all()
        prev_ctx = _previous_publications_context(list(prev_rows))

        # Tons effectifs
        effective_styles = list(styles)
        if "mix" in effective_styles:
            effective_styles = [s for s in effective_styles if s != "mix"]
            if not effective_styles:
                effective_styles = ["stats", "humor"]

        style_lines = "\n".join(
            f"- {STYLE_LABELS.get(s, s)} : {STYLE_INSTRUCTIONS.get(s, '')}" for s in effective_styles
        )
        if custom:
            style_lines += f"\n- Consignes personnalisées de l'utilisateur : {custom}"
        if tone:
            style_lines += f"\n- Ton rédactionnel choisi : {tone}"

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
            f"- Thèmes : {', '.join(strategy.themes) if strategy.themes else 'Non définis'}\n"
            f"- Réseaux : {', '.join(strategy.networks) if strategy.networks else 'Non définis'}\n\n"
            f"Activités récentes Garmin (données réelles, NE PAS INVENTER) :\n"
            f"{json.dumps(recent_activities[:5], ensure_ascii=False, default=str)}\n\n"
            f"Tons demandés :\n{style_lines}{mix_note}\n\n"
            f"Historique des publications précédentes (à éviter) :\n{prev_ctx}\n\n"
            f"Génère 3 propositions de publication Instagram distinctes. "
            f"Pour chaque proposition retourne un objet avec : title, content, hashtags, format (Reel/carrousel/photo/story), "
            f"idee_visuelle, objectif (visibilité/partage/interaction/fidélisation). "
            f"Respecte impérativement le ton demandé et n'invente AUCUNE donnée. "
            f"Réponds uniquement en JSON avec la clé 'proposals'."
        )

        started = datetime.now(timezone.utc)
        try:
            response = await ai_gateway.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.7,
                max_tokens=1800,
            )
        except AIGatewayError as exc:
            logger.warning("[SPORT-PUB-V2] IA indisponible : %s", exc)
            pub.styles = styles
            pub.custom_instructions = custom
            pub.tone_used = tone
            pub.visual_type = visual_type
            pub.photo_id = photo_id
            pub.proposals = []
            pub.provider = None
            pub.model = None
            pub.generated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(pub)
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

        proposals_raw = []
        if isinstance(payload, dict) and isinstance(payload.get("proposals"), list):
            for p in payload["proposals"][:3]:
                if not isinstance(p, dict):
                    continue
                content = str(p.get("content") or "").strip()
                if not content:
                    continue
                proposals_raw.append({
                    "title": str(p.get("title")).strip() if p.get("title") else None,
                    "content": content,
                    "hashtags": str(p.get("hashtags")).strip() if p.get("hashtags") else None,
                    "format": str(p.get("format")).strip() if p.get("format") else "photo",
                    "idee_visuelle": str(p.get("idee_visuelle")).strip() if p.get("idee_visuelle") else None,
                    "objectif": str(p.get("objectif")).strip() if p.get("objectif") else None,
                })

        if not proposals_raw:
            proposals_raw = [{"title": "Publication", "content": text, "hashtags": None, "format": "photo", "idee_visuelle": None, "objectif": None}]

        while len(proposals_raw) < 3:
            proposals_raw.append({"title": None, "content": "", "hashtags": None, "format": "photo", "idee_visuelle": None, "objectif": None})
        proposals_raw = proposals_raw[:3]

        pub.styles = styles
        pub.custom_instructions = custom
        pub.tone_used = tone
        pub.visual_type = visual_type
        pub.photo_id = photo_id
        pub.proposals = proposals_raw
        pub.selected_proposal = 0
        pub.title = proposals_raw[0].get("title")
        pub.content = proposals_raw[0].get("content")
        pub.hashtags = proposals_raw[0].get("hashtags")
        pub.provider = getattr(response, "provider_used", None)
        pub.model = getattr(response, "model_used", None)
        pub.generated_at = datetime.now(timezone.utc)
        pub.status = "draft"
        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def update(self, publication_id: int, data: Any) -> Optional[SportPublication]:
        pub = await self.get_publication(publication_id)
        if pub is None:
            return None
        if data.title is not None:
            pub.title = data.title
        if data.content is not None:
            pub.content = data.content
        if data.hashtags is not None:
            pub.hashtags = data.hashtags
        if hasattr(data, "model_fields_set") and "photo_id" in data.model_fields_set:
            pub.photo_id = data.photo_id
        if data.visual_type is not None:
            pub.visual_type = data.visual_type
        if data.selected_proposal is not None:
            pub.selected_proposal = data.selected_proposal
            # synchronise title/content/hashtags depuis la proposition si l'edition ne fournit pas de texte
            if data.content is None and data.title is None and data.hashtags is None:
                idx = data.selected_proposal
                if isinstance(pub.proposals, list) and 0 <= idx < len(pub.proposals):
                    p = pub.proposals[idx]
                    if isinstance(p, dict):
                        pub.title = p.get("title")
                        pub.content = p.get("content")
                        pub.hashtags = p.get("hashtags")
        if data.styles is not None:
            pub.styles = self._validate_styles(data.styles) or pub.styles
        if data.custom_instructions is not None:
            pub.custom_instructions = data.custom_instructions.strip() or None
        # V2 fields
        if hasattr(data, "tone_used") and data.tone_used is not None:
            pub.tone_used = data.tone_used
        if hasattr(data, "visual_generation_prompt") and data.visual_generation_prompt is not None:
            pub.visual_generation_prompt = data.visual_generation_prompt
        if hasattr(data, "visual_generation_provider") and data.visual_generation_provider is not None:
            pub.visual_generation_provider = data.visual_generation_provider
        if hasattr(data, "scheduled_at") and data.scheduled_at is not None:
            pub.scheduled_at = data.scheduled_at
        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def validate(self, publication_id: int) -> Optional[SportPublication]:
        pub = await self.get_publication(publication_id)
        if pub is None:
            return None
        if not (pub.content or "").strip():
            raise ValueError("Le texte de la publication est vide")
        pub.status = "validated"
        pub.validated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def mark_shared(self, publication_id: int) -> Optional[SportPublication]:
        pub = await self.get_publication(publication_id)
        if pub is None:
            return None
        pub.status = "shared"
        if pub.validated_at is None:
            pub.validated_at = datetime.now(timezone.utc)
        pub.shared_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(pub)
        return pub

    async def delete(self, publication_id: int) -> bool:
        pub = await self.get_publication(publication_id)
        if pub is None:
            return False
        await self.db.delete(pub)
        await self.db.commit()
        return True

    async def generate_card(self, publication_id: int) -> Optional[str]:
        pub = await self.get_publication(publication_id)
        if pub is None:
            return None
        activity = await self.db.execute(select(SportActivity).where(SportActivity.id == pub.activity_id))
        activity = activity.scalar_one_or_none()
        if activity is None:
            return None
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return None
        try:
            os.makedirs(os.path.join(UPLOAD_DIR, PUBLICATIONS_SUBDIR), exist_ok=True)
            path = os.path.join(UPLOAD_DIR, PUBLICATIONS_SUBDIR, f"card_{pub.id}.png")
            img = Image.new("RGB", (1080, 1080), (18, 24, 38))
            draw = ImageDraw.Draw(img)
            try:
                font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
                font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72)
                font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            except Exception:
                font_title = ImageFont.load_default()
                font_big = ImageFont.load_default()
                font_small = ImageFont.load_default()
            # titre
            title = (activity.activity_name or activity.sport_type or "Sortie").strip()
            draw.text((60, 60), title[:40], fill=(255, 255, 255), font=font_title)
            sub = activity.started_at.strftime("%d/%m/%Y") if activity.started_at else ""
            draw.text((60, 120), sub, fill=(180, 190, 210), font=font_small)
            # stats
            stats = []
            if activity.distance_m is not None:
                stats.append(("Distance", f"{activity.distance_m/1000:.1f} km"))
            if activity.elevation_gain_m is not None:
                stats.append(("D+", f"{int(activity.elevation_gain_m)} m"))
            if activity.duration_seconds:
                h, rem = divmod(activity.duration_seconds, 3600)
                m = rem // 60
                stats.append(("Duree", f"{h}h{m:02d}"))
            if activity.avg_pace_sec_km:
                pm = activity.avg_pace_sec_km // 60
                ps = activity.avg_pace_sec_km % 60
                stats.append(("Allure", f"{int(pm)}:{int(ps):02d}/km"))
            if activity.avg_heart_rate:
                stats.append(("FC moy", f"{int(activity.avg_heart_rate)} bpm"))
            if activity.calories:
                stats.append(("Calories", f"{int(activity.calories)} kcal"))
            y = 240
            for label, val in stats[:6]:
                draw.text((60, y), label.upper(), fill=(140, 150, 175), font=font_small)
                draw.text((60, y + 40), val, fill=(255, 255, 255), font=font_big)
                y += 150
            draw.text((60, 1000), "ForgeAI", fill=(90, 100, 125), font=font_small)
            img.save(path)
            pub.card_path = path
            pub.visual_type = "card"
            await self.db.commit()
            await self.db.refresh(pub)
            return path
        except Exception as exc:
            logger.exception("[SPORT-PUB] generation carte impossible : %s", exc)
            return None

    async def get_settings(self) -> dict[str, Any]:
        athlete = await self.get_or_create_athlete()
        cfg = _athlete_settings(athlete)
        await self.db.commit()
        return {
            "notifications_enabled": bool(cfg.get("notifications_enabled", True)),
            "last_styles": list(cfg.get("last_styles") or []),
            "last_custom_instructions": cfg.get("last_custom_instructions"),
        }

    async def update_settings(self, data: Any) -> dict[str, Any]:
        athlete = await self.get_or_create_athlete()
        cfg = _athlete_settings(athlete)
        if data.notifications_enabled is not None:
            cfg["notifications_enabled"] = bool(data.notifications_enabled)
        if data.last_styles is not None:
            cfg["last_styles"] = self._validate_styles(data.last_styles)
        if data.last_custom_instructions is not None:
            v = data.last_custom_instructions.strip() if isinstance(data.last_custom_instructions, str) else data.last_custom_instructions
            cfg["last_custom_instructions"] = v or None
        flag_modified(athlete, "metadata_json")
        await self.db.commit()
        return {
            "notifications_enabled": bool(cfg.get("notifications_enabled", True)),
            "last_styles": list(cfg.get("last_styles") or []),
            "last_custom_instructions": cfg.get("last_custom_instructions"),
        }

    async def notify_new_activities(self) -> int:
        """Envoie une notification par activite recente non encore notifiee (si active)."""
        athlete = await self.get_or_create_athlete()
        cfg = _athlete_settings(athlete)
        if not cfg.get("notifications_enabled", True):
            return 0
        last_id = cfg.get("last_notified_activity_id")
        # activites plus recentes que le dernier id notifie
        query = select(SportActivity).where(SportActivity.athlete_id == athlete.id)
        if last_id:
            query = query.where(SportActivity.id > int(last_id))
        query = query.order_by(SportActivity.id.asc())
        rows = (await self.db.execute(query)).scalars().all()
        if not rows:
            return 0
        sent = 0
        # notifier uniquement les plus recentes (evite le spam massif a la 1ere sync)
        to_notify = rows[-5:]
        for act in to_notify:
            try:
                await NotificationService(self.db).send(
                    user_id=self.current_user.id,
                    title="Nouvelle activite disponible",
                    message="Une publication Instagram peut etre generee a partir de cette sortie.",
                    category="sport_publication",
                    data={"url": f"/sport/publications?activity={act.id}", "activity_id": act.id},
                )
                sent += 1
            except Exception:
                logger.exception("[SPORT-PUB] notification impossible pour activite %s", act.id)
        cfg["last_notified_activity_id"] = rows[-1].id
        flag_modified(athlete, "metadata_json")
        await self.db.commit()
        return sent

    async def list_for_user_id(self, user_id: int) -> int:
        return 0


def style_labels() -> dict[str, str]:
    return dict(STYLE_LABELS)


async def schedule_publication_notifications(user_id: int, athlete_id: int) -> None:
    """Entree pour les hooks post-sync (session propre)."""
    from app.db.session import get_db_context
    from app.models.user import User

    try:
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            if user is None or not user.is_active:
                return
            athlete = await db.get(SportAthlete, athlete_id)
            if athlete is None:
                return
            svc = SportPublicationService(db, user)
            # s'assure que l'athlète courant correspond
            await svc.notify_new_activities()
            await db.commit()
    except Exception:
        logger.exception("[SPORT-PUB] notification post-sync echouee athlete=%s", athlete_id)


def fire_publication_notifications(user_id: int, athlete_id: int) -> None:
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(schedule_publication_notifications(user_id, athlete_id))
            return
    except RuntimeError:
        pass
    # pas d'event loop : rien a faire (les hooks appellent la version async)
    return