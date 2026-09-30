"""Volume du contexte Sport injecté dans les prompts du LLM.

La limite effective constatée en production est de 7 000 tokens d'entrée
(Groq, ITPM ; HTTP 413 au-delà). Le coach IA n'a pas d'outils : tout le
contexte tient dans un prompt unique. L'Agent Sport a 17 outils : son entrée
initiale (système + descriptions d'outils + bref + question) doit laisser de
la place aux résultats d'outils.

Ces tests vérifient qu'un historique réaliste (35 activités, 90 jours de
santé, 15 analyses, objectif, recommandations) reste sous budget.
"""

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.models.sport import (
    SportActivity,
    SportAnalysis,
    SportGarminConnection,
    SportGoal,
    SportHealthDaily,
    SportRecommendation,
)
from app.services.sport import SportService
from app.services.sport_ai import GatewaySportAIProvider

# Rapport observé en production : 49 834 chars ≈ 18 575 tokens.
CHARS_PER_TOKEN = 2.7

# Budgets en tokens d'entrée estimés, marge comprise sous la limite 7 000.
COACH_CONTEXT_MAX_TOKENS = 5_000
COACH_INPUT_MAX_TOKENS = 6_000
AGENT_INPUT_MAX_TOKENS = 6_000

COACH_QUESTION = (
    "Fais une analyse complète de ma situation sportive actuelle. "
    "Consulte mes dernières activités Garmin, mon objectif actif, mes "
    "tendances récentes et donne-moi un plan concret pour la semaine."
)


def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _chars(obj) -> int:
    return len(_dumps(obj))


def _tokens(text: str) -> int:
    return round(len(text) / CHARS_PER_TOKEN)


async def _seed(db, user, *, activities: int = 35, health_days: int = 90,
                analyses: int = 15, recommendations: int = 8) -> int:
    """Jeu réaliste reproduisant le volume constaté en production."""
    service = SportService(db, user)
    athlete = await service.get_or_create_athlete()
    athlete.metadata_json = {"heart_rate_zones": {"max_hr": 190, "rest_hr": 48}}
    today = datetime.now(timezone.utc).date()

    for index in range(activities):
        started = datetime.combine(
            today - timedelta(days=index * 3), datetime.min.time(), tzinfo=timezone.utc,
        ) + timedelta(hours=8)
        db.add(SportActivity(
            athlete_id=athlete.id,
            sport_type="running" if index % 3 else "cycling",
            activity_name=f"Sortie {index}",
            started_at=started,
            duration_seconds=2400 + (index * 67) % 1800,
            distance_m=8000.0 + (index * 431) % 7000,
            elevation_gain_m=60.0 + (index * 13) % 300,
            avg_pace_sec_km=300.0 + (index % 20),
            avg_heart_rate=140 + (index % 12),
            max_heart_rate=165 + (index % 8),
            avg_cadence=170 + (index % 8),
            source_type="garmin",
            external_id=f"ctx-act-{index}",
            metadata_json={},
        ))

    for offset in range(health_days):
        day = today - timedelta(days=offset)
        db.add(SportHealthDaily(
            athlete_id=athlete.id,
            day=day,
            source_type="garmin",
            health_json={
                "heart_rates": {"restingHeartRate": 46 + offset % 5, "maxHR": 180},
                "sleep": {
                    "sleepScore": 70 + offset % 20,
                    "sleepTimeSeconds": 26000 + offset % 40 * 60,
                    "deepSleepSeconds": 5000,
                    "lightSleepSeconds": 12000,
                    "remSleepSeconds": 6000,
                    "awakeTimeSeconds": 2000,
                },
                "hrv": {"hrv": 55 + offset % 15, "status": "balanced"},
                "stress": {"avgStressLevel": 25 + offset % 10, "maxStressLevel": 70},
                "body_battery": {"bodyBatteryValuesArray": [40, 55 + offset % 30]},
                "steps": {"steps": 8000 + offset % 2000, "calories": 2400},
                "readiness": [{"calendarDate": day.isoformat(), "score": 65 + offset % 25, "level": "MODERATE"}],
                "spo2": {"averageSpO2": 96.5},
                "respiration": {"avgWakingRespirationValue": 14.0},
            },
        ))

    paragraph = (
        "La récupération est correcte malgré une charge en légère hausse. "
        "Le sommeil profond reste stable et la variabilité cardiaque ne montre "
        "aucun signe de surmenage. Sur les sept prochains jours, privilégier une "
        "sortie longue à allure modérée et une séance de fractionné courte. "
    )
    for index in range(analyses):
        day = today - timedelta(days=index * 2)
        kind = "morning" if index % 2 else "evening"
        db.add(SportAnalysis(
            athlete_id=athlete.id,
            analysis_type=kind,
            analysis_day=day,
            dedupe_key=f"{kind}:{day.isoformat()}",
            title=f"Analyse du {'matin' if kind == 'morning' else 'soir'} du {day.isoformat()}",
            summary="Récupération correcte, charge stable.",
            content=paragraph * 6,
            provider="groq",
            model="qwen/qwen3.8-27b",
        ))

    goal = SportGoal(
        athlete_id=athlete.id,
        name="10 km en 50 minutes",
        goal_type="race",
        target_value=10.0,
        unit="km",
        target_date=today + timedelta(days=45),
        status="active",
    )
    db.add(goal)

    statuses = ("pending", "accepted", "superseded", "done")
    for index in range(recommendations):
        db.add(SportRecommendation(
            athlete_id=athlete.id,
            objective_id=goal.id if index % 2 == 0 else None,
            category="training" if index % 3 else "recovery",
            recommendation=(
                f"Séance {index} : sortie facile 45 min à allure conversation, "
                "suivie de 4 étirements actifs."
            ),
            reason=f"Motif {index} : écart à l'objectif et charge observée.",
            status=statuses[index % len(statuses)],
            valid_from=datetime.now(timezone.utc) - timedelta(days=index),
            valid_until=datetime.now(timezone.utc) + timedelta(days=7 - index % 4),
            result_json={"state_at_creation": {"activity_count": 3}},
        ))

    await db.commit()
    return athlete.id


async def _coach_context(db, user):
    await _seed(db, user)
    service = SportService(db, user)
    athlete = await service.get_or_create_athlete()
    return await service.build_coach_context(athlete)


def _coach_input(context: dict) -> str:
    """Prompt réellement soumis au LLM par GatewaySportAIProvider."""
    return (
        GatewaySportAIProvider._system_prompt()
        + "\nQuestion: " + COACH_QUESTION
        + "\nContexte JSON:\n" + _dumps(context)
    )


async def test_coach_context_stays_under_token_budget(db_session, admin_user, capsys):
    """35 activités + 90 jours de santé + 15 analyses tiennent sous budget.

    Avant compactage : ~49 653 chars (~17 749 tokens) pour la même graine.
    """
    context = await _coach_context(db_session, admin_user)
    prompt = _coach_input(context)

    with capsys.disabled():
        print("\n--- CONTEXTE COACH (par clé) ---")
        for key, value in context.items():
            print(f"  {key}: {_chars(value)} chars (~{_tokens(_dumps(value))} tokens)")
        print(f"  CONTEXTE: {_chars(context)} chars (~{_tokens(_dumps(context))} tokens)")
        print(f"  ENTREE COACH: {_chars(prompt)} chars (~{_tokens(prompt)} tokens)")

    assert _tokens(_dumps(context)) <= COACH_CONTEXT_MAX_TOKENS
    assert _tokens(prompt) <= COACH_INPUT_MAX_TOKENS
    # Le corps complet des analyses ne part plus dans le prompt.
    assert all("content" not in analysis for analysis in context["recent_analyses"])
    # La santé détaillée reste limitée aux 7 derniers jours.
    assert len(context["health"]["rows"]) <= 7
    assert context["health"]["days_with_data"] == 90


async def test_coach_context_keeps_coaching_information(db_session, admin_user):
    """Le contexte compact conserve objectif, tendances, récupération, recommandations."""
    context = await _coach_context(db_session, admin_user)

    # Objectif actif + progression vers l'objectif.
    assert context["goals"], "objectif actif absent"
    assert context["goals"][0]["name"] == "10 km en 50 minutes"
    profile = context["athlete"]["profile"]
    assert profile.get("goal_analysis"), "progression vers l'objectif absente"

    # Tendances 7 et 30 jours + tendances de période.
    trends = context["period_trends"]
    assert set(trends) == {"d7", "d30"}
    for window in trends.values():
        summary = window["summary"]
        assert summary["activity_count"] > 0
        assert summary["distance_m"] > 0
        assert summary["elevation_gain_m"] is not None
        assert summary["duration_seconds"] is not None
        assert summary["avg_pace_sec_km"] is not None
        assert summary["avg_heart_rate"] is not None
        assert window["change_percent_vs_previous"]["distance_m"] is not None
    assert context["weekly_summary"]["summary"]["activity_count"] > 0
    assert context["monthly_summary"]["summary"]["activity_count"] > 0
    assert context["trends"], "comparaison semaine courante absente"

    # Charge récente.
    assert context["training_load"]["available"] is True
    assert context["weekly_summary"]["training_load"]["available"] is True

    # Récupération + indicateurs santé.
    assert context["recovery"]["available"] is True
    assert context["recovery"]["latest"]["sleep_score"] is not None
    assert context["health"]["summary"]["sleep_score_avg"] is not None
    assert context["health"]["rows"], "indicateurs santé absents"

    # Dernières activités pertinentes.
    assert len(context["recent_activities"]) == 5
    assert context["recent_activities"][0]["activity_count"] == 1

    # Recommandations encore actives + récentes.
    recommendations = context["recommendations"]
    assert len(recommendations["active"]) == 4
    assert {row["status"] for row in recommendations["active"]} <= {"pending", "accepted"}
    assert len(recommendations["recent"]) == 5
    assert recommendations["recent"][0]["recommendation"]

    # Mémoire du coach : titres + résumés des analyses récentes.
    assert 0 < len(context["recent_analyses"]) <= 5
    assert context["recent_analyses"][0]["summary"]


async def test_coach_alerts_flag_issues(db_session, admin_user):
    """Les alertes importantes sont dérivées des données existantes."""
    await _seed(db_session, admin_user)
    service = SportService(db_session, admin_user)
    athlete = await service.get_or_create_athlete()
    today = datetime.now(timezone.utc).date()

    goal = (await db_session.execute(
        select(SportGoal).where(SportGoal.athlete_id == athlete.id)
    )).scalars().first()
    goal.target_date = today - timedelta(days=3)
    db_session.add(SportGarminConnection(
        athlete_id=athlete.id,
        garmin_email="athlete@example.com",
        encrypted_tokens="encrypted",
        status="error",
        last_sync_at=datetime.now(timezone.utc) - timedelta(days=5),
    ))
    await db_session.commit()

    context = await service.build_coach_context(athlete)
    alert_types = {alert["type"] for alert in context["alerts"]}

    assert "objectif_echu" in alert_types
    assert "garmin_deconnecte" in alert_types
    assert len(context["alerts"]) <= 5


async def test_agent_initial_input_stays_under_token_budget(db_session, admin_user, monkeypatch, capsys):
    """Entrée initiale de l'Agent Sport (système + 17 outils + bref + question)."""
    from test_sport_agent import enable_agent, final, responder_for, use_gateway

    from app.services.sport_agent import run_agent_trigger

    await _seed(db_session, admin_user)
    enable_agent(monkeypatch)
    provider = use_gateway(monkeypatch, responder_for(lambda messages: final(summary="mesuré")))

    outcome = await run_agent_trigger(
        db_session, admin_user, "user_request", payload={"question": COACH_QUESTION}
    )
    assert outcome["status"] == "completed"

    first_call = provider.calls[0]
    entry = "\n".join(str(message.get("content") or "") for message in first_call)

    with capsys.disabled():
        print(f"\n--- ENTREE AGENT (1er appel) : {len(entry)} chars (~{_tokens(entry)} tokens) ---")

    assert _tokens(entry) <= AGENT_INPUT_MAX_TOKENS


async def test_details_retrievable_by_existing_tools(db_session, admin_user):
    """Les détails retirés du prompt restent accessibles par les 17 outils existants."""
    from test_sport_agent import _athlete_with_garmin

    from app.services.sport_agent.tool_registry import ToolContext
    from app.services.sport_agent.tools import build_registry

    await _seed(db_session, admin_user)
    await _athlete_with_garmin(db_session, admin_user)
    service = SportService(db_session, admin_user)
    athlete = await service.get_or_create_athlete()
    registry = build_registry()
    ctx = ToolContext(db=db_session, user=admin_user, athlete=athlete)

    # Corps complet des analyses (retiré du prompt, récupérable sur demande).
    assert len(registry.names()) == 17
    lite = await registry.call(ctx, "list_previous_analyses", {"limit": 3})
    assert lite.ok, lite.error
    assert all("content" not in row for row in lite.data["analyses"])
    analyses = await registry.call(ctx, "list_previous_analyses", {"limit": 3, "detail": True})
    assert analyses.ok, analyses.error
    assert any((row.get("content") or "") for row in analyses.data["analyses"]), "contenu complet des analyses inaccessible"

    # Activités détaillées (seules 5 résumées partent dans le prompt).
    activities = await registry.call(ctx, "get_recent_activities", {"days": 90, "limit": 30})
    assert activities.ok, activities.error
    assert activities.data["count"] > 5

    # Historique complet sur fenêtre large.
    history = await registry.call(ctx, "get_training_history", {"days": 90})
    assert history.ok, history.error
    assert history.data["summary"]["activity_count"] > 0

    # Santé jour par jour au-delà des 7 jours du prompt.
    health = await registry.call(ctx, "get_health_data", {"days": 90})
    assert health.ok, health.error
    assert health.data["days_with_data"] == 90
    assert len(health.data["rows"]) > 7
