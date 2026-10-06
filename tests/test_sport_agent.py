"""Tests de l'Agent Sport autonome (orchestrateur, outils, déclencheurs)."""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.models.maintenance import AIConversation, AIMessage
from app.models.notification import Notification
from app.models.sport import (
    SportActivity,
    SportAgentExecution,
    SportAnalysis,
    SportAthlete,
    SportGarminConnection,
    SportGoal,
    SportRecommendation,
)
from app.services.ai_gateway import AIGateway, ai_gateway
from app.services.ai_gateway.tool_protocol import build_tool_instructions, parse_final, parse_tool_calls
from app.services.sport import SportService
from app.services.sport_agent import run_agent_trigger
from app.services.sport_analysis_service import SportAnalysisService, run_sport_analysis_cycle

MORNING_NOW = datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)  # 12:00 Europe/Paris

ANALYSIS_JSON = {
    "title": "Analyse du matin",
    "notification": "Nuit correcte, charge stable.",
    "summary": "Récupération correcte.",
    "content": "## Résumé\nRécupération correcte.",
}


# --------------------------------------------------------------------------- #
# Passerelle IA scriptée (le vrai protocole d'outils est exercé)
# --------------------------------------------------------------------------- #


class ScriptedProvider:
    """Fournisseur IA factice branché dans la vraie AI Gateway."""

    name = "groq"

    def __init__(self, responder):
        self.responder = responder
        self.calls: list[list[dict]] = []

    @property
    def is_available(self) -> bool:
        return True

    async def chat(self, *, model, messages, temperature, max_tokens):
        self.calls.append([dict(message) for message in messages])
        return self.responder(messages), 8, 4


def use_gateway(monkeypatch, responder):
    provider = ScriptedProvider(responder)
    gateway = AIGateway(settings=get_settings(), providers={"groq": provider})
    monkeypatch.setattr("app.services.ai_gateway.gateway.get_ai_gateway", lambda: gateway)
    return provider


def enable_agent(monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "SPORT_AGENT_ENABLED", True)


def is_tool_round(messages: list[dict]) -> bool:
    return any((m.get("content") or "").startswith("Résultats des outils") for m in messages)


def is_agent_call(messages: list[dict]) -> bool:
    system = messages[0].get("content", "") if messages else ""
    return "OUTILS DISPONIBLES" in system


def tool_calls(*calls: tuple[str, dict]) -> str:
    return json.dumps({"tool_calls": [{"name": name, "arguments": args} for name, args in calls]})


def final(**decision) -> str:
    payload = {"reasoning": "test", "summary": "décision", "actions": [], "follow_up": False}
    payload.update(decision)
    return json.dumps({"final": payload})


def responder_for(agent_fn):
    def _respond(messages: list[dict]) -> str:
        if is_agent_call(messages):
            return agent_fn(messages)
        return json.dumps(ANALYSIS_JSON)

    return _respond


async def _athlete_with_garmin(db, user) -> int:
    athlete = await SportService(db, user).get_or_create_athlete()
    db.add(
        SportGarminConnection(
            athlete_id=athlete.id,
            garmin_email="athlete@example.com",
            encrypted_tokens="encrypted",
            status="connected",
        )
    )
    await db.commit()
    return athlete.id


async def _goal(db, athlete_id: int) -> SportGoal:
    goal = SportGoal(
        athlete_id=athlete_id,
        name="10 km en 50 minutes",
        goal_type="race",
        target_value=10.0,
        unit="km",
        status="active",
    )
    db.add(goal)
    await db.commit()
    return goal


# --------------------------------------------------------------------------- #
# 1. Traçabilité d'une exécution
# --------------------------------------------------------------------------- #


async def test_agent_execution_is_traced(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("get_active_objectives", {}))
        return final(summary="Objectif 10 km vérifié")

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "morning")

    assert outcome["status"] == "completed"
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    assert execution is not None
    assert execution.trigger == "morning"
    assert execution.status == "completed"
    assert execution.provider == "groq"
    assert execution.model
    assert execution.finished_at is not None
    assert execution.step_count >= 1

    phases = [step["phase"] for step in execution.steps_json]
    assert phases[0] == "observe"
    for expected in ("tool_call", "decide", "reassess", "terminate"):
        assert expected in phases, phases
    assert execution.result_json["answer"] == ""


# --------------------------------------------------------------------------- #
# 2. Budget d'étapes maximal
# --------------------------------------------------------------------------- #


async def test_agent_respects_max_steps_budget(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    max_steps = get_settings().SPORT_AGENT_MAX_STEPS

    def agent_fn(messages):
        return final(summary="toujours à revoir", follow_up=True)

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "evening")
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])

    # État terminal budgété : le repli historique le considère comme produit.
    assert execution.status == "budget_exhausted"
    assert outcome["status"] == "budget_exhausted"
    assert execution.step_count == max_steps
    assert any(step["phase"] == "budget" for step in execution.steps_json)
    assert any(step["phase"] == "terminate" for step in execution.steps_json)


# --------------------------------------------------------------------------- #
# 3. Outil refusé par RBAC : la boucle continue
# --------------------------------------------------------------------------- #


async def test_agent_continues_when_tool_denied_by_rbac(db_session, auth_user, monkeypatch):
    enable_agent(monkeypatch)

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("get_recent_activities", {}))
        return final(summary="Données indisponibles, conclusion sans activité")

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, auth_user, "morning")

    assert outcome["status"] == "completed"
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    tools = execution.result_json["tool_calls"]
    assert tools[0]["name"] == "get_recent_activities"
    assert tools[0]["ok"] is False
    assert "permission_denied" in tools[0]["error"]


# --------------------------------------------------------------------------- #
# 4. Aucune notification inutile
# --------------------------------------------------------------------------- #


async def test_agent_sends_no_notification_without_reason(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    use_gateway(monkeypatch, responder_for(lambda messages: final(summary="RAS")))

    outcome = await run_agent_trigger(db_session, admin_user, "evening")

    assert outcome["status"] == "completed"
    assert outcome["actions"] == 0
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert notifications == []


# --------------------------------------------------------------------------- #
# 5. Recommandation reliée à l'objectif actif
# --------------------------------------------------------------------------- #


async def test_agent_creates_recommendation_linked_to_objective(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    goal = await _goal(db_session, athlete_id)

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("get_active_objectives", {}))
        return final(
            summary="Séance tempo à 10 km de l'objectif",
            actions=[
                {
                    "type": "create_recommendation",
                    "recommendation": "Séance tempo de 6 km jeudi",
                    "reason": "Préparation 10 km",
                    "category": "training",
                    "valid_days": 7,
                }
            ],
        )

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "morning")

    rows = (await db_session.execute(select(SportRecommendation))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "pending"
    assert row.athlete_id == athlete_id
    assert row.objective_id == goal.id
    assert row.execution_id == outcome["execution_id"]
    assert row.valid_until is not None
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    assert execution.objective_id == goal.id
    assert any(step["phase"] == "verification" and step["verified"] for step in execution.steps_json)


# --------------------------------------------------------------------------- #
# 6. Réévaluation : remplacement d'une recommandation
# --------------------------------------------------------------------------- #


async def test_agent_replaces_recommendation_on_reassessment(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    await _goal(db_session, athlete_id)

    db_session.add(
        SportRecommendation(
            athlete_id=athlete_id,
            user_id=admin_user.id,
            category="training",
            recommendation="Sortie longue dimanche",
            reason="volume",
            status="pending",
        )
    )
    await db_session.commit()
    stale = (await db_session.execute(select(SportRecommendation))).scalars().first()

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("get_previous_recommendations", {}))
        return final(
            summary="Recommandation remplacée (fatigue)",
            actions=[
                {
                    "type": "update_recommendation",
                    "recommendation_id": stale.id,
                    "status": "superseded",
                    "reason": "Fatigue accumulée",
                }
            ],
        )

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "evening")

    assert outcome["status"] == "completed"
    await db_session.refresh(stale)
    assert stale.status == "superseded"
    assert "Fatigue accumulée" in (stale.reason or "")
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    verification = [step for step in execution.steps_json if step["phase"] == "verification"]
    assert verification and verification[0]["verified"] is True


# --------------------------------------------------------------------------- #
# 7. Statuts réservés à l'utilisateur
# --------------------------------------------------------------------------- #


async def test_agent_action_rejects_status_reserved_to_user(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    db_session.add(
        SportRecommendation(
            athlete_id=athlete_id,
            user_id=admin_user.id,
            category="training",
            recommendation="Séance planifiée",
            reason="",
            status="pending",
        )
    )
    await db_session.commit()
    pending = (await db_session.execute(select(SportRecommendation))).scalars().first()

    def agent_fn(messages):
        return final(
            actions=[
                {
                    "type": "update_recommendation",
                    "recommendation_id": pending.id,
                    "status": "accepted",
                }
            ]
        )

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "morning")

    await db_session.refresh(pending)
    assert pending.status == "pending"
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    action = [step for step in execution.steps_json if step["phase"] == "action"][0]
    assert action["ok"] is False
    assert "statut_non_autorise" in action["error"]


# --------------------------------------------------------------------------- #
# 8. Demande utilisateur : réponse conversationnelle, sans notification
# --------------------------------------------------------------------------- #


async def test_agent_user_request_answers_without_notification(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)

    def agent_fn(messages):
        return final(
            summary="Objectif du moment",
            answer="Ton objectif actif est un 10 km en 50 minutes.",
            actions=[{"type": "send_notification", "title": "Objectif", "message": "10 km"}],
        )

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(
        db_session,
        admin_user,
        "user_request",
        payload={"question": "Quel est mon objectif ?"},
        history=[{"role": "user", "content": "Bonjour"}],
    )

    assert outcome["status"] == "completed"
    assert outcome["answer"] == "Ton objectif actif est un 10 km en 50 minutes."
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert notifications == []
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    action = [step for step in execution.steps_json if step["phase"] == "action"][0]
    assert action["skipped"] == "reponse_conversationnelle"


# --------------------------------------------------------------------------- #
# 9. Rétrocompatibilité de la passerelle sans outils
# --------------------------------------------------------------------------- #


async def test_gateway_without_tools_keeps_legacy_contract(monkeypatch):
    provider = use_gateway(monkeypatch, lambda messages: "Réponse simple")

    response = await ai_gateway.generate(prompt="Bonjour", system_prompt="Tu es l'assistant.")

    assert response.text == "Réponse simple"
    assert response.provider_used == "groq"
    assert response.tool_calls == []
    system = provider.calls[0][0]["content"]
    assert "OUTILS DISPONIBLES" not in system
    assert "PROTOCOLE D'OUTILS" not in system


# --------------------------------------------------------------------------- #
# 10. Protocole d'outils
# --------------------------------------------------------------------------- #


def test_tool_protocol_parses_calls_and_final():
    calls = parse_tool_calls('```json\n{"tool_calls": [{"name": "get_sleep", "arguments": {"day": 3}}]}\n```')
    assert calls == [{"name": "get_sleep", "arguments": {"day": 3}}]

    assert parse_final('{"final": {"summary": "ok", "actions": []}}') == {"summary": "ok", "actions": []}
    assert parse_final('{"summary": "direct"}') == {"summary": "direct"}
    assert parse_final("Réponse en texte libre") is None

    instructions = build_tool_instructions(
        [{"name": "get_sleep", "description": "Sommeil", "input_schema": {"type": "object"}}]
    )
    assert "get_sleep" in instructions
    assert "PROTOCOLE D'OUTILS" in instructions


# --------------------------------------------------------------------------- #
# 11. Cycle : repli obligatoire sur le job historique
# --------------------------------------------------------------------------- #


async def test_cycle_falls_back_to_legacy_when_agent_fails(db_session, admin_user, monkeypatch):
    async def _fake_generate(**kwargs):
        class _Response:
            text = json.dumps(ANALYSIS_JSON)
            provider_used = "test-provider"
            model_used = "test-model"
            tokens_output = 5

        return _Response()

    enable_agent(monkeypatch)
    called: list[str] = []

    async def failing_agent(db, user, trigger, payload=None, history=None, registry=None):
        called.append(trigger)
        return {"status": "fallback", "created_analyses": 0, "execution_id": None, "answer": ""}

    monkeypatch.setattr("app.services.sport_agent.run_agent_trigger", failing_agent)
    await _athlete_with_garmin(db_session, admin_user)

    # Le cycle : l'agent échoue, l'analyse historique prend le relais.
    monkeypatch.setattr(ai_gateway, "generate", _fake_generate)
    stats = await run_sport_analysis_cycle(db_session, MORNING_NOW)

    assert called == ["morning"]
    assert stats["morning"] == 1
    assert stats["errors"] == 0
    analyses = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert [row.analysis_type for row in analyses] == ["morning"]

    # Aucune exécution d'agent n'a été créée (simulée) : le repli est réel.
    executions = (await db_session.execute(select(SportAgentExecution))).scalars().all()
    assert executions == []


# --------------------------------------------------------------------------- #
# 12. Cycle : l'agent produit l'analyse, le job historique ne tourne pas
# --------------------------------------------------------------------------- #


async def test_cycle_runs_agent_and_skips_legacy(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    await _athlete_with_garmin(db_session, admin_user)

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("generate_daily_analysis", {"kind": "morning"}))
        return final(summary="Analyse du matin produite")

    use_gateway(monkeypatch, responder_for(agent_fn))

    # Le job historique ne doit être appelé QUE par l'outil de l'agent,
    # jamais directement par le cycle.
    original_analyze = SportAnalysisService.analyze_morning
    calls = {"count": 0}

    async def counting_analyze(self, notify: bool = True):
        calls["count"] += 1
        return await original_analyze(self, notify=notify)

    monkeypatch.setattr(SportAnalysisService, "analyze_morning", counting_analyze)

    stats = await run_sport_analysis_cycle(db_session, MORNING_NOW)
    assert calls["count"] == 1
    assert stats["morning"] == 1
    assert stats["errors"] == 0

    analyses = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert [row.analysis_type for row in analyses] == ["morning"]
    executions = (await db_session.execute(select(SportAgentExecution))).scalars().all()
    assert len(executions) == 1
    assert executions[0].status == "completed"
    assert executions[0].result_json["created_analyses"] == 1

    # Cycle suivant : cooldown, une seule exécution pour ce déclencheur.
    stats_again = await run_sport_analysis_cycle(db_session, MORNING_NOW)
    assert stats_again["morning"] == 0
    executions_after = (await db_session.execute(select(SportAgentExecution))).scalars().all()
    assert len(executions_after) == 1


# --------------------------------------------------------------------------- #
# 13. Assistant IA global : routage vers l'agent + module déduit
# --------------------------------------------------------------------------- #


async def test_ai_chat_routes_sport_question_to_agent(client, admin_headers, db_session, monkeypatch):
    enable_agent(monkeypatch)

    def agent_fn(messages):
        return final(
            summary="Objectif",
            answer="Ton objectif actif est un 10 km en 50 minutes.",
        )

    use_gateway(monkeypatch, responder_for(agent_fn))

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Quel est mon objectif de la semaine ?"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Ton objectif actif est un 10 km en 50 minutes."

    conversation = await db_session.get(AIConversation, data["conversation_id"])
    assert conversation.module == "sport"
    messages = (
        await db_session.execute(
            select(AIMessage).where(AIMessage.conversation_id == conversation.id).order_by(AIMessage.id)
        )
    ).scalars().all()
    assert [message.role for message in messages] == ["user", "assistant"]


# --------------------------------------------------------------------------- #
# 14. Drapeau désactivé : l'agent n'est jamais réveillé
# --------------------------------------------------------------------------- #


async def test_agent_stays_disabled_when_feature_flag_off(db_session, admin_user, monkeypatch):
    # Drapeau éteint (les jobs historiques prennent alors le relais) : le
    # réveil est refusé avant toute création d'exécution.
    monkeypatch.setattr(get_settings(), "SPORT_AGENT_ENABLED", False)
    outcome = await run_agent_trigger(db_session, admin_user, "morning")

    assert outcome["status"] == "disabled"
    assert outcome["execution_id"] is None
    executions = (await db_session.execute(select(SportAgentExecution))).scalars().all()
    assert executions == []


# --------------------------------------------------------------------------- #
# 15. Déclencheur "activité" du cycle : l'agent prend le relais du job
# --------------------------------------------------------------------------- #


async def test_cycle_activity_trigger_wakes_agent(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    # Fenêtres matin/soir désactivées : seul le déclencheur activité est dû.
    monkeypatch.setattr(get_settings(), "SPORT_MORNING_ANALYSIS_ENABLED", False)
    monkeypatch.setattr(get_settings(), "SPORT_EVENING_ANALYSIS_ENABLED", False)

    base = MORNING_NOW.replace(tzinfo=None)
    activity = SportActivity(
        athlete_id=athlete_id,
        sport_type="running",
        started_at=base - timedelta(minutes=30),
        duration_seconds=1200,
        distance_m=10000,
        source_type="garmin",
        created_at=base - timedelta(minutes=20),
    )
    db_session.add(activity)
    await db_session.commit()

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("generate_activity_analysis", {"activity_id": activity.id}))
        return final(summary="Débrief de la sortie produit")

    use_gateway(monkeypatch, responder_for(agent_fn))

    original = SportAnalysisService.analyze_recent_activities
    legacy_calls = {"count": 0}

    async def counting_analyze(self, now=None):
        legacy_calls["count"] += 1
        return await original(self, now)

    monkeypatch.setattr(SportAnalysisService, "analyze_recent_activities", counting_analyze)

    stats = await run_sport_analysis_cycle(db_session, MORNING_NOW)

    assert stats["activities"] == 1
    assert stats["errors"] == 0
    # Le job historique n'est pas appelé : l'agent a produit l'analyse.
    assert legacy_calls["count"] == 0

    executions = (await db_session.execute(select(SportAgentExecution))).scalars().all()
    assert len(executions) == 1
    execution = executions[0]
    assert execution.trigger == "activity"
    assert execution.status == "completed"
    assert execution.result_json["created_analyses"] == 1

    # Le brief remis à l'agent contient bien les activités en attente.
    observe = next(step for step in execution.steps_json if step["phase"] == "observe")
    assert observe["brief"]["payload"]["activity_ids"] == [activity.id]

    analyses = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert [row.analysis_type for row in analyses] == ["activity"]
    assert analyses[0].activity_id == activity.id


# --------------------------------------------------------------------------- #
# 16. Événement métier : objective_created + cooldown
# --------------------------------------------------------------------------- #


async def test_objective_created_event_wakes_agent(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    from app.services.sport_agent.events import emit_agent_event

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("get_active_objectives", {}))
        return final(summary="Objectif pris en compte")

    use_gateway(monkeypatch, responder_for(agent_fn))

    first = await emit_agent_event(
        db_session, admin_user, athlete_id, "objective_created", {"goal_id": None}
    )
    assert first["status"] == "completed"
    execution = await db_session.get(SportAgentExecution, first["execution_id"])
    assert execution.trigger == "objective_created"

    # Deuxième émission dans la fenêtre de cooldown : aucun nouveau réveil.
    second = await emit_agent_event(db_session, admin_user, athlete_id, "objective_created", {})
    assert second["status"] == "cooldown"
    executions = (await db_session.execute(select(SportAgentExecution))).scalars().all()
    assert len(executions) == 1


# --------------------------------------------------------------------------- #
# 17. Événement métier : training_missed émis une seule fois
# --------------------------------------------------------------------------- #


async def test_training_missed_event_is_emitted_once(db_session, admin_user):
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    now = datetime.now(timezone.utc)
    db_session.add(
        SportRecommendation(
            athlete_id=athlete_id,
            user_id=admin_user.id,
            category="training",
            recommendation="Fractionné 6x400m",
            status="pending",
            valid_from=now - timedelta(days=14),
            valid_until=now - timedelta(days=2),
        )
    )
    await db_session.commit()

    from app.services.sport_agent.events import collect_missed_training_events

    first = await collect_missed_training_events(db_session, athlete_id, now)
    assert [trigger for trigger, _payload in first] == ["training_missed"]
    assert first[0][1]["valid_until"] is not None
    await db_session.commit()

    # Le marquage dans result_json empêche tout ré-émission.
    second = await collect_missed_training_events(db_session, athlete_id, now)
    assert second == []


# --------------------------------------------------------------------------- #
# 18. Événements post-synchronisation Garmin
# --------------------------------------------------------------------------- #


async def test_post_sync_events_include_garmin_and_training_completed(db_session, admin_user):
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    athlete = await db_session.get(SportAthlete, athlete_id)
    now = datetime.now(timezone.utc)
    base = (now - timedelta(days=1)).replace(tzinfo=None, hour=18, minute=0, second=0, microsecond=0)
    db_session.add(
        SportActivity(
            athlete_id=athlete_id,
            sport_type="running",
            started_at=base,
            duration_seconds=3000,
            distance_m=8000,
            source_type="garmin",
            created_at=base,
        )
    )
    db_session.add(
        SportRecommendation(
            athlete_id=athlete_id,
            user_id=admin_user.id,
            category="training",
            recommendation="Sortie facile 8 km",
            status="accepted",
            valid_from=now - timedelta(days=7),
            valid_until=now + timedelta(days=7),
        )
    )
    await db_session.commit()

    from app.services.sport_agent.events import collect_post_sync_events

    events = await collect_post_sync_events(db_session, admin_user, athlete, 3)
    triggers = [trigger for trigger, _payload in events]
    assert triggers == ["garmin_sync", "training_completed"]
    assert events[0][1]["imported_count"] == 3
    assert events[1][1]["activity_id"] is not None


# --------------------------------------------------------------------------- #
# 19. objective_id doit appartenir à l'athlète de l'exécution
# --------------------------------------------------------------------------- #


async def test_create_recommendation_rejects_foreign_objective(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    other_athlete = SportAthlete(user_id=None, display_name="Autre athlète")
    db_session.add(other_athlete)
    await db_session.flush()
    foreign_goal = SportGoal(
        athlete_id=other_athlete.id,
        name="Objectif d'un autre athlète",
        goal_type="race",
        status="active",
    )
    db_session.add(foreign_goal)
    await db_session.commit()

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(
                (
                    "create_training_recommendation",
                    {"recommendation": "Séance au seuil", "objective_id": foreign_goal.id},
                )
            )
        return final(summary="Refusé, je continue")

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "user_request")
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    tools = execution.result_json["tool_calls"]
    assert tools[0]["ok"] is False
    assert "objectif_non_autorise" in tools[0]["error"]

    rows = (
        await db_session.execute(
            select(SportRecommendation).where(SportRecommendation.athlete_id == athlete_id)
        )
    ).scalars().all()
    assert rows == []


# --------------------------------------------------------------------------- #
# 20. Anti-duplication : aucune seconde recommandation active identique
# --------------------------------------------------------------------------- #


async def test_create_recommendation_detects_duplicate(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    await _athlete_with_garmin(db_session, admin_user)

    def agent_fn(messages):
        if not is_tool_round(messages):
            args = {"recommendation": "Fractionné 6x400m sur piste", "reason": "écart à l'objectif"}
            return tool_calls(
                ("create_training_recommendation", dict(args)),
                ("create_training_recommendation", dict(args)),
            )
        return final(summary="Une seule séance proposée")

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "user_request")
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    tools = execution.result_json["tool_calls"]

    assert tools[0]["ok"] is True
    assert tools[1]["ok"] is True
    assert tools[1]["result"]["duplicate"] is True
    assert tools[1]["result"]["existing_id"] == tools[0]["result"]["id"]

    rows = (await db_session.execute(select(SportRecommendation))).scalars().all()
    assert len(rows) == 1


# --------------------------------------------------------------------------- #
# 21. Analyse toujours notifiée + publiée dans l'assistant + vérifiée en base
# --------------------------------------------------------------------------- #


async def test_generate_analysis_notifies_and_publishes_to_assistant(
    db_session, admin_user, monkeypatch
):
    enable_agent(monkeypatch)
    await _athlete_with_garmin(db_session, admin_user)

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(("generate_daily_analysis", {"kind": "morning"}))
        return final(summary="Analyse du matin produite")

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "morning")
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    tools = execution.result_json["tool_calls"]
    assert tools[0]["ok"] is True
    # L'analyse est confirmée en base : elle compte pour le repli du cycle.
    assert execution.result_json["created_analyses"] == 1
    verifications = [
        item for item in execution.result_json["verifications"] if item["type"] == "generate_analysis"
    ]
    assert verifications and verifications[0]["verified"] is True

    analyses = (await db_session.execute(select(SportAnalysis))).scalars().all()
    assert len(analyses) == 1
    # Chaque analyse notifie l'utilisateur (contrat matin / soir / sortie).
    assert analyses[0].notification_sent is True
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifications) == 1
    assert notifications[0].category == "sport_analysis"

    # L'analyse est publiée dans la conversation « Coach & Analyses ».
    conversation = await db_session.scalar(
        select(AIConversation).where(AIConversation.module == "coach")
    )
    assert conversation is not None
    assert conversation.user_id == admin_user.id
    feed = (
        await db_session.execute(
            select(AIMessage).where(AIMessage.conversation_id == conversation.id)
        )
    ).scalars().all()
    assert len(feed) == 1
    assert feed[0].role == "assistant"
    assert "Analyse du matin" in feed[0].content

    # Deuxième réveil (soir) : nouvelle analyse → nouvelle notification,
    # toujours un seul message par analyse dans l'assistant.
    def agent_fn_evening(messages):
        if not is_tool_round(messages):
            return tool_calls(("generate_daily_analysis", {"kind": "evening"}))
        return final(summary="Analyse du soir notifiée")

    use_gateway(monkeypatch, responder_for(agent_fn_evening))
    outcome_evening = await run_agent_trigger(db_session, admin_user, "evening")
    assert outcome_evening["status"] == "completed"
    notifications = (await db_session.execute(select(Notification))).scalars().all()
    assert len(notifications) == 2
    assert {item.category for item in notifications} == {"sport_analysis"}
    feed = (
        await db_session.execute(
            select(AIMessage).where(AIMessage.conversation_id == conversation.id)
        )
    ).scalars().all()
    assert len(feed) == 2


# --------------------------------------------------------------------------- #
# 22. Tâches de fond FastAPI : les scheduleurs doivent être des coroutines
# --------------------------------------------------------------------------- #


async def test_schedule_event_helpers_are_coroutines():
    """Starlette exécute les tâches de fond synchrones dans un threadpool, où
    ``asyncio.create_task`` échouerait : les scheduleurs doivent donc être async."""
    from app.services.sport_agent.events import (
        fire_post_sync_events,
        schedule_agent_event,
        schedule_post_sync_events,
    )

    assert asyncio.iscoroutinefunction(schedule_agent_event)
    assert asyncio.iscoroutinefunction(schedule_post_sync_events)
    assert not asyncio.iscoroutinefunction(fire_post_sync_events)


# --------------------------------------------------------------------------- #
# 23. Expiration des échéances avant l'anti-doublon
# --------------------------------------------------------------------------- #


async def test_create_recommendation_expires_stale_before_duplicate(db_session, admin_user, monkeypatch):
    enable_agent(monkeypatch)
    athlete_id = await _athlete_with_garmin(db_session, admin_user)
    now = datetime.now(timezone.utc)
    # Recommandation échue mais encore « pending » : même texte que la nouvelle.
    db_session.add(
        SportRecommendation(
            athlete_id=athlete_id,
            user_id=admin_user.id,
            category="training",
            recommendation="Fractionné 6x400m sur piste",
            status="pending",
            valid_from=now - timedelta(days=30),
            valid_until=now - timedelta(days=1),
        )
    )
    await db_session.commit()

    def agent_fn(messages):
        if not is_tool_round(messages):
            return tool_calls(
                (
                    "create_training_recommendation",
                    {"recommendation": "Fractionné 6x400m sur piste"},
                )
            )
        return final(summary="Nouvelle séance proposée")

    use_gateway(monkeypatch, responder_for(agent_fn))

    outcome = await run_agent_trigger(db_session, admin_user, "user_request")
    execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
    tools = execution.result_json["tool_calls"]
    assert tools[0]["ok"] is True
    assert tools[0]["result"]["duplicate"] is False
    assert tools[0]["result"]["expired_stale_count"] == 1

    rows = (await db_session.execute(select(SportRecommendation))).scalars().all()
    assert sorted(row.status for row in rows) == ["expired", "pending"]


# --------------------------------------------------------------------------- #
# 24. Conseils ponctuels du coach : plafond quotidien + publication assistant
# --------------------------------------------------------------------------- #


async def test_coach_tip_respects_daily_limit_and_reaches_assistant(
    db_session, admin_user, monkeypatch
):
    enable_agent(monkeypatch)
    await _athlete_with_garmin(db_session, admin_user)

    def agent_fn(messages):
        return final(
            summary="Conseil personnalisé",
            actions=[
                {
                    "type": "send_coach_tip",
                    "title": "Hydratation",
                    "message": "Bois 500 ml d'eau dans la journée.",
                }
            ],
        )

    use_gateway(monkeypatch, responder_for(agent_fn))

    action_outcomes = []
    for _ in range(3):
        outcome = await run_agent_trigger(db_session, admin_user, "morning")
        execution = await db_session.get(SportAgentExecution, outcome["execution_id"])
        action_outcomes.append(execution.result_json["actions"][0])

    limit = get_settings().COACH_TIP_DAILY_LIMIT
    assert limit == 2
    assert action_outcomes[0]["ok"] is True
    assert action_outcomes[1]["ok"] is True
    # Troisième conseil du jour : refusé par le quota.
    assert action_outcomes[2]["ok"] is False
    assert "quota_conseils_atteint" in (action_outcomes[2].get("error") or "")

    tips = [
        item
        for item in (await db_session.execute(select(Notification))).scalars().all()
        if item.category == "coach_tip"
    ]
    assert len(tips) == limit
    assert tips[0].data_json.get("url") == "/ai"

    # Chaque conseil envoyé est publié dans la conversation de l'assistant.
    conversation = await db_session.scalar(
        select(AIConversation).where(AIConversation.module == "coach")
    )
    assert conversation is not None
    feed = (
        await db_session.execute(
            select(AIMessage).where(AIMessage.conversation_id == conversation.id)
        )
    ).scalars().all()
    assert len(feed) == limit
    assert all(item.role == "assistant" for item in feed)
    assert "Hydratation" in feed[0].content
