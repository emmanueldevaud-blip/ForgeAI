"""Orchestrateur multi-tours de l'Agent Sport.

Boucle réelle : OBSERVE → DECIDE → ACT → VERIFY → REASSESS (→ nouveau tour)
avec un nombre maximal d'étapes, un budget d'outils, une protection contre
les appels répétés et une limite de temps.

La décision n'est pas codée en dur : elle est produite par le modèle via la
passerelle IA, qui exécute les outils demandés jusqu'à ce que le modèle rende
sa décision finale. Les actions sont ensuite exécutées, vérifiées en base,
puis réévaluées.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.models.notification import Notification
from app.models.sport import SportAgentExecution, SportAnalysis, SportGoal, SportRecommendation
from app.services.ai_gateway import AIGatewayError, ai_gateway
from app.services.ai_gateway.tool_protocol import parse_final
from app.services.sport_agent.context import RunContext
from app.services.sport_agent.prompts import ACTION_TYPES, AGENT_SYSTEM_PROMPT, build_mission
from app.services.sport_agent.tool_registry import ToolResult

logger = logging.getLogger(__name__)

MAX_ACTIONS_PER_STEP = 5
TOOL_ROUNDS_PER_STEP = 3
SAME_TOOL_CALL_LIMIT = 2
_ACTION_TOOL = {
    "create_recommendation": "create_training_recommendation",
    "update_recommendation": "update_recommendation",
    "send_notification": "send_notification",
    "send_coach_tip": "send_coach_tip",
}
# Actions sans effet pendant une conversation : la réponse est déjà affichée.
_CONVERSATIONAL_SKIP = frozenset({"send_notification", "send_coach_tip"})


def json_safe(value: Any) -> Any:
    """Rend une valeur stockable en colonne JSON (dates, ORM, etc.)."""
    return json.loads(json.dumps(value, default=str))


class AgentOrchestrator:
    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.steps: list[dict[str, Any]] = []
        self.tool_records: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.verifications: list[dict[str, Any]] = []
        self.answer: str = ""
        self.provider: str | None = None
        self.model: str | None = None
        self.step_count = 0
        self.max_steps = max(1, ctx.settings.SPORT_AGENT_MAX_STEPS)
        self.tool_budget = max(1, ctx.settings.SPORT_AGENT_MAX_TOOL_CALLS)
        self.tools_used = 0
        self._tool_calls_seen: dict[str, int] = {}
        self._forced_retries = 0
        self.started = time.monotonic()
        self.deadline = self.started + max(5, ctx.settings.SPORT_AGENT_TIMEOUT_SECONDS)

    # ------------------------------------------------------------------ #
    # Boucle
    # ------------------------------------------------------------------ #

    async def execute(self) -> SportAgentExecution:
        logger.info(
            "[SPORT-AGENT] event=started trigger=%s user=%s athlete=%s max_steps=%d budget_outils=%d",
            self.ctx.trigger,
            self.ctx.user.id,
            self.ctx.athlete.id,
            self.max_steps,
            self.tool_budget,
        )
        status = "completed"
        error: str | None = None
        try:
            brief = await self._observe()
            status = await self._loop(brief)
        except AIGatewayError as exc:
            status = "fallback"
            error = f"{type(exc).__name__}: {str(exc) or 'passerelle IA indisponible'}"
            logger.warning("[SPORT-AGENT] event=failed status=fallback error=%s", type(exc).__name__)
        except Exception as exc:  # l'agent doit survivre à une erreur inattendue
            status = "failed"
            error = f"{type(exc).__name__}: {str(exc) or 'erreur inattendue'}"
            logger.exception("[SPORT-AGENT] event=failed status=failed trigger=%s", self.ctx.trigger)
            try:
                await self.ctx.db.rollback()
            except Exception:
                logger.exception("[SPORT-AGENT] event=rollback_failed")
        self._record("terminate", self.step_count, status=status, error=error)
        await self._finish(status, error)
        return self.ctx.execution

    async def _loop(self, brief: dict[str, Any]) -> str:
        status = "completed"
        for step in range(1, self.max_steps + 1):
            if time.monotonic() > self.deadline:
                self._record("timeout", step, elapsed_seconds=round(time.monotonic() - self.started, 1))
                return "timeout"
            self.step_count = step
            decision = await self._decide(brief, step)
            self.decisions.append(json_safe(decision))
            actions = await self._act(decision, step)
            self.actions.extend(actions)
            verifications = await self._verify(actions, step)
            self.verifications.extend(verifications)
            follow_up = self._reassess(decision, verifications, step)
            if not follow_up:
                break
        else:
            # Boucle sortie sans ``break`` : les étapes sont épuisées alors que
            # la décision finale demandait encore à poursuivre. L'état est donc
            # terminal mais budgété, et non « completed ».
            self._record("budget", self.step_count, reason="max_steps_atteint")
            status = "budget_exhausted"
        return status

    # ------------------------------------------------------------------ #
    # OBSERVE
    # ------------------------------------------------------------------ #

    async def _observe(self) -> dict[str, Any]:
        goals = list(
            (
                await self.ctx.db.execute(
                    select(SportGoal).where(
                        SportGoal.athlete_id == self.ctx.athlete.id,
                        SportGoal.status == "active",
                    )
                )
            ).scalars().all()
        )
        counts = {
            status: count
            for status, count in (
                await self.ctx.db.execute(
                    select(SportRecommendation.status, func.count(SportRecommendation.id))
                    .where(SportRecommendation.athlete_id == self.ctx.athlete.id)
                    .group_by(SportRecommendation.status)
                )
            ).all()
        }
        previous = (
            await self.ctx.db.execute(
                select(SportAgentExecution)
                .where(
                    SportAgentExecution.athlete_id == self.ctx.athlete.id,
                    SportAgentExecution.id != self.ctx.execution.id,
                )
                .order_by(SportAgentExecution.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        active_recommendations = list(
            (
                await self.ctx.db.execute(
                    select(SportRecommendation)
                    .where(
                        SportRecommendation.athlete_id == self.ctx.athlete.id,
                        SportRecommendation.status.in_(("pending", "accepted")),
                    )
                    .order_by(SportRecommendation.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()
        )
        recovery = await self._recovery_snapshot()
        payload = {key: value for key, value in self.ctx.payload.items() if key != "question"}
        brief = {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "trigger": self.ctx.trigger,
            "payload": payload,
            "active_objectives": [
                {
                    "id": goal.id,
                    "name": goal.name,
                    "goal_type": goal.goal_type,
                    "target_value": goal.target_value,
                    "unit": goal.unit,
                    "target_date": goal.target_date.isoformat() if goal.target_date else None,
                }
                for goal in goals
            ],
            "recommendation_counts_by_status": counts,
            # Mémoire active : ce que l'athlète a déjà en cours, avec l'état de
            # l'athlète au moment où chaque recommandation a été créée.
            "active_recommendations": [
                {
                    "id": row.id,
                    "status": row.status,
                    "category": row.category,
                    "recommendation": row.recommendation,
                    "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                    "valid_until": row.valid_until.isoformat() if row.valid_until else None,
                    "objective_id": row.objective_id,
                    "state_at_creation": (
                        (row.result_json or {}).get("state_at_creation")
                        if isinstance(row.result_json, dict)
                        else None
                    ),
                }
                for row in active_recommendations
            ],
            # État de récupération actuel (utile pour juger une variation).
            "recovery": recovery,
            "previous_execution": (
                {
                    "id": previous.id,
                    "trigger": previous.trigger,
                    "status": previous.status,
                    "summary": (previous.summary or "")[:200],
                    "finished_at": previous.finished_at.isoformat() if previous.finished_at else None,
                }
                if previous is not None
                else None
            ),
        }
        self._record("observe", 0, brief=json_safe(brief))
        logger.info(
            "[SPORT-AGENT] event=step phase=observe objectifs=%d recommandations=%s",
            len(goals),
            counts or "{}",
        )
        return brief

    async def _recovery_snapshot(self) -> dict[str, Any]:
        """Contexte de récupération pour le brief ; jamais bloquant."""
        from app.services.sport import SportService

        try:
            recovery = await SportService(self.ctx.db, self.ctx.user).recovery_context()
        except Exception:
            logger.warning("[SPORT-AGENT] event=recovery_snapshot_failed", exc_info=True)
            return {"available": False, "reason": "indisponible"}
        return recovery if isinstance(recovery, dict) else {"available": False}

    # ------------------------------------------------------------------ #
    # DECIDE
    # ------------------------------------------------------------------ #

    async def _decide(self, brief: dict[str, Any], step: int) -> dict[str, Any]:
        question = self.ctx.payload.get("question")
        mission = build_mission(self.ctx.trigger, brief, question if isinstance(question, str) else None)
        kwargs: dict[str, Any] = {
            "system_prompt": AGENT_SYSTEM_PROMPT,
            "tools": self.ctx.registry.specs(),
            "tool_executor": self._tool_executor,
            "max_tool_rounds": TOOL_ROUNDS_PER_STEP,
            "max_tool_calls": self.tool_budget - self.tools_used,
        }
        if self.ctx.history:
            kwargs["history"] = [*self.ctx.history, {"role": "user", "content": mission}]
        else:
            kwargs["prompt"] = mission

        response = await ai_gateway.generate(**kwargs)
        self.provider = response.provider_used
        self.model = response.model_used
        decision = parse_final(response.text)
        if decision is None:
            decision = self._unstructured_decision(response.text)
        summary = str(decision.get("summary") or decision.get("answer") or "")[:400]
        self._record(
            "decide",
            step,
            summary=summary,
            actions=len(decision.get("actions") or []) if isinstance(decision.get("actions"), list) else 0,
            follow_up=bool(decision.get("follow_up")),
            tools_called=len([record for record in self.tool_records if record.get("step") == step]),
            structured=decision.get("reasoning") != "reponse_non_structuree",
        )
        logger.info(
            "[SPORT-AGENT] event=decision step=%d actions=%d follow_up=%s",
            step,
            len(decision.get("actions") or []) if isinstance(decision.get("actions"), list) else 0,
            bool(decision.get("follow_up")),
        )
        if self.ctx.trigger == "user_request" and not self.answer:
            self.answer = str(decision.get("answer") or decision.get("summary") or "")[:4000]
        return decision

    def _unstructured_decision(self, text: str) -> dict[str, Any]:
        if self.ctx.trigger == "user_request":
            return {
                "reasoning": "reponse_texte_libre",
                "summary": "",
                "answer": (text or "").strip()[:4000],
                "actions": [],
                "follow_up": False,
            }
        return {
            "reasoning": "reponse_non_structuree",
            "summary": "",
            "actions": [],
            "follow_up": False,
        }

    async def _tool_executor(self, name: str, arguments: dict[str, Any]) -> Any:
        step = self.step_count
        if self.tools_used >= self.tool_budget:
            logger.warning("[SPORT-AGENT] event=tool_call name=%s ok=false reason=budget_atteint", name)
            return {"ok": False, "error": "budget_outil_atteint"}
        key = f"{name}:{json.dumps(arguments, ensure_ascii=False, sort_keys=True, default=str)}"
        seen = self._tool_calls_seen.get(key, 0)
        if seen >= SAME_TOOL_CALL_LIMIT:
            logger.warning("[SPORT-AGENT] event=tool_call name=%s ok=false reason=appel_repete", name)
            return {"ok": False, "error": "appel_repete"}
        self._tool_calls_seen[key] = seen + 1

        started = time.monotonic()
        result: ToolResult = await self.ctx.registry.call(self.ctx.tool_context(), name, arguments)
        duration_ms = int((time.monotonic() - started) * 1000)
        self.tools_used += 1
        record = {
            "step": step,
            "name": name,
            "ok": result.ok,
            "duration_ms": duration_ms,
            "result": _slim_result(result.data) if result.ok else None,
            "error": result.error,
        }
        self.tool_records.append(record)
        self._record(
            "tool_call",
            step,
            name=name,
            ok=result.ok,
            duration_ms=duration_ms,
            error=result.error,
            result=record["result"],
        )
        return result.as_dict()

    # ------------------------------------------------------------------ #
    # ACT
    # ------------------------------------------------------------------ #

    async def _act(self, decision: dict[str, Any], step: int) -> list[dict[str, Any]]:
        raw_actions = decision.get("actions")
        if not isinstance(raw_actions, list):
            raw_actions = []
        results: list[dict[str, Any]] = []
        for raw in raw_actions[:MAX_ACTIONS_PER_STEP]:
            if not isinstance(raw, dict):
                continue
            action_type = str(raw.get("type") or "").strip()
            entry: dict[str, Any] = {"type": action_type, "ok": False, "step": step}
            if action_type not in ACTION_TYPES:
                entry["error"] = f"type_inconnu:{action_type or 'vide'}"
            elif action_type in _CONVERSATIONAL_SKIP and self.ctx.trigger == "user_request":
                # En conversation, l'athlète a déjà la réponse sous les yeux :
                # notification et conseil poussés seraient un doublon.
                entry["skipped"] = "reponse_conversationnelle"
            else:
                arguments = {key: value for key, value in raw.items() if key != "type"}
                result = await self.ctx.registry.call(self.ctx.tool_context(), _ACTION_TOOL[action_type], arguments)
                entry["ok"] = result.ok
                entry["error"] = result.error
                entry["target_id"] = _target_id(action_type, result)
                entry["result"] = _slim_result(result.data) if result.ok else None
            results.append(entry)
            self._record(
                "action",
                step,
                type=action_type,
                ok=entry["ok"],
                target_id=entry.get("target_id"),
                error=entry.get("error"),
                skipped=entry.get("skipped"),
            )
            logger.info(
                "[SPORT-AGENT] event=action step=%d type=%s ok=%s",
                step,
                action_type or "vide",
                entry["ok"],
            )
        if results:
            await self.ctx.db.commit()
        return results

    # ------------------------------------------------------------------ #
    # VERIFY
    # ------------------------------------------------------------------ #

    async def _verify(self, actions: list[dict[str, Any]], step: int) -> list[dict[str, Any]]:
        verifications: list[dict[str, Any]] = []
        for entry in actions:
            record: dict[str, Any] = {
                "type": entry.get("type"),
                "target_id": entry.get("target_id"),
                "action_ok": entry.get("ok", False),
                # True = confirmé en base, False = échec, None = non vérifiable
                "verified": None,
            }
            if entry.get("ok") and entry.get("target_id"):
                record["verified"] = await self._verify_target(entry)
            verifications.append(record)
            self._record(
                "verification",
                step,
                type=record["type"],
                target_id=record["target_id"],
                verified=record["verified"],
            )
            logger.info(
                "[SPORT-AGENT] event=verification step=%d type=%s target=%s ok=%s",
                step,
                record.get("type"),
                record.get("target_id"),
                record["verified"],
            )
        verifications.extend(await self._verify_generated(step))
        return verifications

    async def _verify_generated(self, step: int) -> list[dict[str, Any]]:
        """Vérifie que chaque analyse « générée » existe réellement en base.

        Le résultat d'un outil ``generate_*`` est cru : une ligne absente ou un
        ``analysis_id`` manquant ne doit pas compter comme une analyse créée
        (sinon le repli historique serait court-circuité à tort).
        """
        verifications: list[dict[str, Any]] = []
        for record in self.tool_records:
            if record.get("step") != step or not record.get("ok"):
                continue
            if not str(record.get("name") or "").startswith("generate_"):
                continue
            if not (record.get("result") or {}).get("created"):
                continue
            analysis_id = (record.get("result") or {}).get("analysis_id")
            verified = False
            if analysis_id is not None:
                row = await self.ctx.db.get(SportAnalysis, analysis_id)
                verified = row is not None and row.athlete_id == self.ctx.athlete.id
            record["verified"] = verified
            verifications.append({
                "type": "generate_analysis",
                "target_id": analysis_id,
                "action_ok": True,
                "verified": verified,
                "tool": record.get("name"),
            })
            self._record(
                "verification",
                step,
                type="generate_analysis",
                target_id=analysis_id,
                verified=verified,
                tool=record.get("name"),
            )
            logger.info(
                "[SPORT-AGENT] event=verification step=%d type=generate_analysis target=%s ok=%s",
                step,
                analysis_id,
                verified,
            )
        return verifications

    async def _verify_target(self, entry: dict[str, Any]) -> bool:
        action_type = entry.get("type")
        target_id = entry.get("target_id")
        if action_type == "create_recommendation":
            row = await self.ctx.db.get(SportRecommendation, target_id)
            return row is not None and row.athlete_id == self.ctx.athlete.id
        if action_type == "update_recommendation":
            row = await self.ctx.db.get(SportRecommendation, target_id)
            expected = (entry.get("result") or {}).get("status")
            return row is not None and (expected is None or row.status == expected)
        if action_type in ("send_notification", "send_coach_tip"):
            row = await self.ctx.db.get(Notification, target_id)
            return row is not None and row.user_id == self.ctx.user.id
        return False

    # ------------------------------------------------------------------ #
    # REASSESS
    # ------------------------------------------------------------------ #

    def _reassess(self, decision: dict[str, Any], verifications: list[dict[str, Any]], step: int) -> bool:
        follow_up = bool(decision.get("follow_up"))
        failed = [item for item in verifications if item.get("action_ok") and item.get("verified") is False]
        forced = False
        if failed and not follow_up and self._forced_retries < 1:
            follow_up = True
            forced = True
            self._forced_retries += 1
        self._record(
            "reassess",
            step,
            follow_up=follow_up,
            failed_verifications=len(failed),
            forced_retry=forced,
            remaining_steps=self.max_steps - step,
        )
        return follow_up

    # ------------------------------------------------------------------ #
    # Persistance
    # ------------------------------------------------------------------ #

    async def _finish(self, status: str, error: str | None) -> None:
        execution = self.ctx.execution
        execution.status = status
        execution.step_count = self.step_count
        execution.error = error
        execution.provider = self.provider
        execution.model = self.model
        execution.steps_json = json_safe(self.steps)
        execution.summary = self._summary(status)
        execution.result_json = json_safe(
            {
                "answer": self.answer,
                "decisions": self.decisions,
                "actions": self.actions,
                "verifications": self.verifications,
                "tool_calls": self.tool_records,
                "created_analyses": self._created_analyses(),
                "objective_id": self._objective_id(),
                "duration_ms": int((time.monotonic() - self.started) * 1000),
            }
        )
        execution.objective_id = self._objective_id()
        execution.finished_at = datetime.now(timezone.utc)
        try:
            await self.ctx.db.commit()
        except Exception:
            await self.ctx.db.rollback()
            logger.exception("[SPORT-AGENT] event=completed_persist_failed status=%s", status)
        logger.info(
            "[SPORT-AGENT] event=finished status=%s trigger=%s steps=%d outils=%d actions=%d",
            status,
            self.ctx.trigger,
            self.step_count,
            len(self.tool_records),
            len(self.actions),
        )

    def _summary(self, status: str) -> str:
        if self.ctx.trigger == "user_request" and self.answer:
            return self.answer[:400]
        for decision in reversed(self.decisions):
            summary = str(decision.get("summary") or "").strip()
            if summary:
                return summary[:400]
        return f"Exécution {self.ctx.trigger} terminée ({status})"

    def _created_analyses(self) -> int:
        """Analyses réellement créées ET confirmées en base (voir ``_verify_generated``)."""
        count = 0
        for record in self.tool_records:
            if not (
                record.get("ok")
                and str(record.get("name", "")).startswith("generate_")
                and (record.get("result") or {}).get("created")
            ):
                continue
            # Une vérification a été posée pour cet enregistrement : elle doit
            # être concluante pour que l'analyse compte.
            if "verified" in record and record["verified"] is not True:
                continue
            count += 1
        return count

    def _objective_id(self) -> int | None:
        for action in self.actions:
            result = action.get("result") or {}
            if action.get("type") == "create_recommendation" and result.get("objective_id"):
                return int(result["objective_id"])
        return None

    def _record(self, phase: str, step: int, **fields: Any) -> None:
        self.steps.append({"phase": phase, "step": step, "at": datetime.now(timezone.utc).isoformat(), **fields})


def _target_id(action_type: str, result: ToolResult) -> int | None:
    if not result.ok or not isinstance(result.data, dict):
        return None
    key = "notification_id" if action_type in ("send_notification", "send_coach_tip") else "id"
    value = result.data.get(key)
    if value is None and action_type == "create_recommendation":
        # Anti-duplication : rien n'est créé, la recommandation existante est
        # renvoyée (elle sert de cible de vérification).
        value = result.data.get("existing_id")
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _slim_result(data: Any) -> dict[str, Any]:
    """Trace compacte d'un résultat d'outil (pas de données massives en base)."""
    if not isinstance(data, dict):
        return {}
    keys = (
        "id",
        "found",
        "created",
        "already_existed",
        "duplicate",
        "existing_id",
        "existing_status",
        "expired_stale_count",
        "analysis_id",
        "activity_id",
        "notification_id",
        "count",
        "status",
        "objective_id",
        "push_sent",
        "connected",
    )
    return {key: data[key] for key in keys if key in data}
