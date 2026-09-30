"""Outils mémoire des décisions : recommandations persistées par l'agent.

C'est la mémoire de l'agent (et non l'historique sportif) : elle permet de
retrouver les recommandations en cours, les recommandations non réalisées et
celles qui ont été remplacées lors d'une réévaluation.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.models.sport import SportActivity, SportGoal, SportRecommendation
from app.services.sport_agent.tool_registry import ToolContext, ToolSpec

# Statuts que l'agent peut poser seul : il ne remplace que ses propres
# recommandations. « accepted / completed / skipped » reflètent l'action de
# l'utilisateur et ne sont pas décidables par l'agent.
AGENT_STATUSES = ("superseded", "cancelled", "expired")
# Recommandations encore en cours : c'est le périmètre de la mémoire active.
ACTIVE_STATUSES = ("pending", "accepted")
# Règle simple d'anti-duplication : identique après normalisation, ou
# recouvrement de vocabulaire >= 80 %. Aucune analyse sémantique.
SIMILARITY_THRESHOLD = 0.8
_TOKENS_RE = re.compile(r"[a-z0-9]+")


def recommendation_dict(item: SportRecommendation) -> dict[str, Any]:
    result = item.result_json if isinstance(item.result_json, dict) else {}
    return {
        "id": item.id,
        "status": item.status,
        "category": item.category,
        "recommendation": item.recommendation,
        "reason": item.reason,
        "objective_id": item.objective_id,
        "execution_id": item.execution_id,
        "valid_from": item.valid_from.isoformat() if item.valid_from else None,
        "valid_until": item.valid_until.isoformat() if item.valid_until else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        # État de l'athlète au moment de la recommandation : permet de comparer
        # « état alors » vs « état maintenant » lors d'un nouvel événement.
        "state_at_creation": result.get("state_at_creation"),
    }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(_TOKENS_RE.findall(stripped.lower()))


def is_similar_recommendation(left: str, right: str) -> bool:
    """Règle déterministe : identique après normalisation ou Jaccard >= 0.8."""
    left_norm, right_norm = _normalize(left), _normalize(right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    left_tokens, right_tokens = set(left_norm.split()), set(right_norm.split())
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    return overlap >= SIMILARITY_THRESHOLD


async def _active_objective_id(ctx: ToolContext) -> int | None:
    """Objectif actif de la page Objectifs (lié automatiquement aux décisions)."""
    goals = [goal for goal in await ctx.service.list_goals() if (goal.status or "active") == "active"]
    if not goals:
        return None
    if len(goals) == 1:
        return goals[0].id
    dated = [goal for goal in goals if goal.target_date]
    if dated:
        return min(dated, key=lambda goal: goal.target_date).id
    return None


async def _validate_objective(ctx: ToolContext, objective_id: Any) -> int:
    """L'objectif fourni doit exister ET appartenir à l'athlète de l'exécution."""
    try:
        goal_id = int(objective_id)
    except (TypeError, ValueError):
        raise ValueError(f"objectif_introuvable:{objective_id}") from None
    goal = await ctx.db.get(SportGoal, goal_id)
    if goal is None:
        raise ValueError(f"objectif_introuvable:{goal_id}")
    if goal.athlete_id != ctx.athlete.id:
        raise ValueError(f"objectif_non_autorise:{goal_id}")
    return goal.id


async def _find_duplicate(ctx: ToolContext, text: str) -> SportRecommendation | None:
    """Recommandation active du même athlète quasi identique (anti-doublon)."""
    rows = (
        (
            await ctx.db.execute(
                select(SportRecommendation)
                .where(
                    SportRecommendation.athlete_id == ctx.athlete.id,
                    SportRecommendation.status.in_(ACTIVE_STATUSES),
                )
                .order_by(SportRecommendation.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    for row in rows:
        if is_similar_recommendation(text, row.recommendation):
            return row
    return None


async def _expire_stale(ctx: ToolContext, now: datetime) -> int:
    """Expiration déterministe des recommandations échues (statut « expired »).

    Ne touche jamais aux statuts posés par l'utilisateur (accepted/completed/
    skipped) : seules les recommandations encore « pending » sont expirées.
    """
    rows = (
        (
            await ctx.db.execute(
                select(SportRecommendation).where(
                    SportRecommendation.athlete_id == ctx.athlete.id,
                    SportRecommendation.status == "pending",
                    SportRecommendation.valid_until.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    expired = 0
    for row in rows:
        valid_until = _aware(row.valid_until)
        if valid_until is None or valid_until >= now:
            continue
        row.status = "expired"
        row.result_json = {
            **(row.result_json or {}),
            "expired_at": now.isoformat(),
            "expired_by_execution": ctx.payload.get("execution_id"),
        }
        expired += 1
    if expired:
        await ctx.db.flush()
    return expired


async def _state_snapshot(ctx: ToolContext, now: datetime) -> dict[str, Any]:
    """État de l'athlète au moment de la création de la recommandation."""
    snapshot: dict[str, Any] = {
        "day": now.date().isoformat(),
        "activities_last_7d": 0,
        "latest_activity": None,
        "readiness_score": None,
        "sleep_minutes": None,
    }
    try:
        since = now - timedelta(days=7)
        latest = (
            (
                await ctx.db.execute(
                    select(SportActivity)
                    .where(
                        SportActivity.athlete_id == ctx.athlete.id,
                        SportActivity.started_at >= since,
                    )
                    .order_by(SportActivity.started_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if latest is not None:
            snapshot["latest_activity"] = {
                "id": latest.id,
                "type": getattr(latest, "sport_type", None) or getattr(latest, "activity_type", None),
                "started_at": latest.started_at.isoformat() if latest.started_at else None,
                "distance_m": getattr(latest, "distance_m", None),
            }
        snapshot["activities_last_7d"] = len(
            (
                await ctx.db.execute(
                    select(SportActivity.id).where(
                        SportActivity.athlete_id == ctx.athlete.id,
                        SportActivity.started_at >= since,
                    )
                )
            ).scalars().all()
        )
        recovery = await ctx.service.recovery_context()
        if isinstance(recovery, dict) and recovery.get("available"):
            latest_recovery = recovery.get("latest") or {}
            snapshot["readiness_score"] = latest_recovery.get("readiness_score")
            snapshot["sleep_minutes"] = latest_recovery.get("sleep_total_minutes")
    except Exception:
        # Le snapshot ne doit jamais faire échouer la création : il est
        # informatif uniquement.
        pass
    return snapshot



async def get_previous_recommendations(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    limit = max(1, min(int(args.get("limit") or 10), 50))
    query = select(SportRecommendation).where(SportRecommendation.athlete_id == ctx.athlete.id)
    status = str(args.get("status") or "").strip()
    if status:
        query = query.where(SportRecommendation.status == status)
    result = await ctx.db.execute(
        query.order_by(SportRecommendation.created_at.desc()).limit(limit)
    )
    rows = list(result.scalars().all())
    return {"count": len(rows), "recommendations": [recommendation_dict(row) for row in rows]}


async def create_training_recommendation(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("recommendation") or "").strip()
    if not text:
        raise ValueError("recommendation_manquante")
    valid_days = max(1, min(int(args.get("valid_days") or 7), 90))
    now = datetime.now(timezone.utc)

    # 1. Objectif : fourni → validé (existence + appartenance à l'athlète),
    #    absent → objectif actif lié automatiquement (comportement historique).
    objective_id: int | None = None
    if args.get("objective_id") is not None:
        objective_id = await _validate_objective(ctx, args.get("objective_id"))
    else:
        objective_id = await _active_objective_id(ctx)

    # 2. Expiration des échéances dépassées : une recommandation échue ne doit
    #    pas bloquer la création d'une nouvelle (anti-doublon ci-dessous).
    expired_stale = await _expire_stale(ctx, now)

    # 3. Anti-duplication : pas de seconde recommandation active quasi
    #    identique pour le même athlète.
    duplicate = await _find_duplicate(ctx, text)
    if duplicate is not None:
        return {
            "duplicate": True,
            "existing_id": duplicate.id,
            "existing_status": duplicate.status,
            "objective_id": duplicate.objective_id,
            "expired_stale_count": expired_stale,
        }

    # 4. État de l'athlète à l'instant T (base d'une réévaluation future).
    snapshot = await _state_snapshot(ctx, now)

    item = SportRecommendation(
        athlete_id=ctx.athlete.id,
        user_id=ctx.user.id,
        objective_id=objective_id,
        execution_id=ctx.payload.get("execution_id"),
        category=str(args.get("category") or "training")[:40],
        recommendation=text[:4000],
        reason=str(args.get("reason") or "")[:4000],
        status="pending",
        valid_from=now,
        valid_until=now + timedelta(days=valid_days),
        result_json={
            "state_at_creation": snapshot,
            "expired_stale_count": expired_stale,
        },
    )
    ctx.db.add(item)
    await ctx.db.flush()
    return {
        "duplicate": False,
        "id": item.id,
        "status": item.status,
        "objective_id": item.objective_id,
        "execution_id": item.execution_id,
        "valid_until": item.valid_until.isoformat() if item.valid_until else None,
        "expired_stale_count": expired_stale,
    }


async def update_recommendation(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    recommendation_id = int(args.get("recommendation_id") or 0)
    status = str(args.get("status") or "").strip().lower()
    if status not in AGENT_STATUSES:
        raise ValueError(f"statut_non_autorise:{status or 'vide'}")
    result = await ctx.db.execute(
        select(SportRecommendation).where(
            SportRecommendation.id == recommendation_id,
            SportRecommendation.athlete_id == ctx.athlete.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return {"found": False, "recommendation_id": recommendation_id}
    item.status = status
    if args.get("reason"):
        item.reason = str(args.get("reason"))[:4000]
    item.result_json = {
        **(item.result_json or {}),
        "superseded_by_execution": ctx.payload.get("execution_id"),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await ctx.db.flush()
    return {"found": True, "id": item.id, "status": item.status}


SPECS: list[ToolSpec] = [
    ToolSpec(
        name="get_previous_recommendations",
        description=(
            "Recommandations de l'agent (mémoire) : en cours, non réalisées, remplacées ou expirées. "
            "À consulter avant de proposer une nouvelle séance."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Filtrer par statut : pending, accepted, completed, skipped, expired, superseded, cancelled",
                },
                "limit": {"type": "integer", "description": "Défaut 10, max 50"},
            },
        },
        handler=get_previous_recommendations,
        permission="sport.access",
        access="read",
    ),
    ToolSpec(
        name="create_training_recommendation",
        description=(
            "Crée une recommandation persistée (séance, récupération, hygiène de vie). "
            "Liée automatiquement à l'objectif actif si aucun objective_id n'est fourni ; "
            "un objective_id fourni doit appartenir à l'athlète. Si une recommandation active "
            "quasi identique existe, aucune n'est créée : le résultat contient duplicate=true "
            "et existing_id."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "recommendation": {"type": "string", "description": "Conseil concret à donner à l'athlète"},
                "reason": {"type": "string", "description": "Justification basée sur les données observées"},
                "category": {"type": "string", "description": "training | recovery | other"},
                "valid_days": {"type": "integer", "description": "Durée de validité en jours (défaut 7)"},
                "objective_id": {
                    "type": "integer",
                    "description": "Objectif lié (sinon objectif actif) ; doit appartenir à l'athlète",
                },
            },
            "required": ["recommendation"],
        },
        handler=create_training_recommendation,
        permission="sport.access",
        access="write",
    ),
    ToolSpec(
        name="update_recommendation",
        description=(
            "Met à jour le statut d'une recommandation existante. L'agent ne peut utiliser que "
            "superseded (remplacée), cancelled ou expired (expirée)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "recommendation_id": {"type": "integer"},
                "status": {"type": "string", "description": "superseded | cancelled | expired"},
                "reason": {"type": "string"},
            },
            "required": ["recommendation_id", "status"],
        },
        handler=update_recommendation,
        permission="sport.access",
        access="write",
    ),
]
