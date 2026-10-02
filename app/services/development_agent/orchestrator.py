"""Orchestrateur de l'Agent Développement."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings, Settings
from app.models.user import User
from app.models.development import DevelopmentAgentExecution, DevelopmentTask, DevelopmentTaskStatus
from app.services.ai_gateway import AIGateway, ai_gateway, AIGatewayError
from app.services.ai_gateway.tool_protocol import build_tool_instructions, parse_final, parse_tool_calls
from app.services.development_agent.context import RunContext
from app.models.development import DevelopmentAgentExecution as ExecutionModel, DevelopmentTask
from app.services.development_agent.opencode import OpenCodeClient
from app.services.development_agent.prompts import DEVELOPMENT_SYSTEM_PROMPT, build_mission
from app.services.development_agent.tool_registry import DevelopmentToolRegistry, ToolCallRecord
from app.services.development_agent.tools import build_registry

logger = logging.getLogger(__name__)

# Configuration par défaut
MAX_STEPS = 10
TOOL_ROUNDS_PER_STEP = 3
TOOL_BUDGET = 20


class DevelopmentOrchestrator:
    """Orchestrateur de l'Agent Développement."""

    def __init__(
        self,
        ctx: RunContextModel,
        max_steps: int = MAX_STEPS,
        tool_budget: int = TOOL_BUDGET,
    ):
        self.ctx = ctx
        self.max_steps = max_steps
        self.tool_budget = tool_budget
        self.tools_used = 0
        self.decisions: list[dict[str, Any]] = []
        self.actions: list[dict[str, Any]] = []
        self.started = time.monotonic()
        self.deadline = self.started + ctx.settings.DEVELOPMENT_AGENT_TIMEOUT_SECONDS
        self.step_count = 0

    async def run(self) -> str:
        """Exécute l'agent jusqu'à completion ou budget épuisé."""
        logger.info(
            "[DEV-AGENT] task=%s trigger=%s status=started",
            self.ctx.task.id,
            self.ctx.task.status,
        )

        # Phase d'observation initiale
        brief = await self._observe()
        status = await self._loop(brief)

        # Reporter la réponse finale de l'agent dans le bilan d'exécution
        final_decision = next(
            (d for d in reversed(self.decisions) if d.get("answer") or d.get("summary")),
            None,
        ) or {}
        if final_decision.get("answer"):
            brief["answer"] = final_decision["answer"]
        if final_decision.get("summary"):
            brief["summary"] = final_decision["summary"]

        self.ctx.execution.status = status
        self.ctx.execution.finished_at = datetime.now(timezone.utc)
        self.ctx.execution.step_count = self.step_count
        self.ctx.execution.steps_json = [
            {"phase": "observe", "brief": brief, **d} for d in self.decisions
        ]
        self.ctx.execution.result_json = {
            "summary": brief.get("summary"),
            "answer": brief.get("answer"),
            "modified_files": self.ctx.task.modified_files,
            "diff_summary": self.ctx.task.diff_summary,
            "test_results": self.ctx.task.test_results,
        }

        await self.ctx.db.commit()
        logger.info("[DEV-AGENT] task=%s status=%s steps=%d", self.ctx.task.id, status, self.step_count)
        return status

    async def _loop(self, brief: dict[str, Any]) -> str:
        status = "completed"
        for step in range(1, self.max_steps + 1):
            if time.monotonic() > self.deadline:
                await self._record("timeout", step, elapsed_seconds=round(time.monotonic() - self.started, 1))
                return "timeout"

            self.step_count = step
            decision = await self._decide(brief, step)
            self.decisions.append(decision)

            actions = await self._act(decision, step)
            self.actions.extend(actions)

            verifications = await self._verify(actions, step)
            # self.verifications.extend(verifications)

            follow_up = self._reassess(decision, verifications, step)
            if not follow_up:
                break
        else:
            await self._record("budget", self.step_count, reason="max_steps_atteint")
            status = "budget_exhausted"
        return status

    # ------------------------------------------------------------------ #
    # OBSERVE
    # ------------------------------------------------------------------ #

    async def _observe(self) -> dict[str, Any]:
        """Construit le bref état initial."""
        task = self.ctx.task
        repo_status = {}

        # Statut repository si pas déjà dans le payload
        if "repo_status" not in self.ctx.payload:
            from app.services.development_agent.tools.reading import get_repository_status
            from app.services.development_agent.tool_registry import ToolContext
            tool_ctx = self.ctx.tool_context()
            repo_result = await get_repository_status(tool_ctx, {})
            repo_status = repo_result
            self.ctx.payload["repo_status"] = repo_result
        else:
            repo_status = self.ctx.payload["repo_status"]

        brief = {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "trigger": self.ctx.task.status,  # pending, analyzing, etc.
            "payload": self.ctx.payload,
            "task": {
                "id": task.id,
                "title": task.title,
                "request": task.request,
                "status": task.status,
                "branch": task.branch,
                "repository": task.repository,
            },
            "repository": repo_status,
            "opencode_session": task.opencode_session_id,
            "modified_files": task.modified_files,
            "diff_summary": task.diff_summary,
            "test_results": task.test_results,
        }

        await self._record("observe", 0, brief=brief)
        logger.info("[DEV-AGENT] task=%s observe branch=%s files=%d",
                    task.id, task.branch or "master", len(task.modified_files))
        return brief

    # ------------------------------------------------------------------ #
    # DECIDE
    # ------------------------------------------------------------------ #

    async def _decide(self, brief: dict[str, Any], step: int) -> dict[str, Any]:
        """Demande une décision au modèle via AI Gateway."""
        mission = build_mission(self.ctx.task.status, brief)
        kwargs: dict[str, Any] = {
            "system_prompt": DEVELOPMENT_SYSTEM_PROMPT,
            "tools": self.ctx.registry.specs(),
            "tool_executor": self._tool_executor,
            "max_tool_rounds": TOOL_ROUNDS_PER_STEP,
            "max_tool_calls": self.tool_budget - self.tools_used,
        }

        gateway = self._get_gateway()
        response = await gateway.generate(
            prompt=mission,
            **kwargs,
        )

        if response.tool_calls:
            # Le modèle a demandé des outils - on les exécute dans _act
            return {"type": "tool_calls", "calls": response.tool_calls, "raw": response.text}

        # Réponse finale
        final = parse_final(response.text)
        if final:
            return {"type": "final", **final}

        # Réponse texte simple
        return {"type": "text", "summary": response.text, "reasoning": "", "actions": [], "follow_up": False}

    def _get_gateway(self) -> AIGateway:
        return ai_gateway

    async def _tool_executor(self, name: str, arguments: dict[str, Any]) -> Any:
        """Exécute un outil via le registre."""
        if self.tools_used >= self.tool_budget:
            return {"error": "Budget outils épuisé"}

        self.tools_used += 1
        tool_ctx = self.ctx.tool_context()
        result = await self.ctx.registry.call(tool_ctx, name, arguments)

        record = ToolCallRecord(
            name=name,
            ok=result.ok,
            arguments=arguments,
            error=result.error,
        )
        await self._record("tool_call", self.step_count, tool=record.as_dict())

        if result.ok:
            return result.data
        return {"error": result.error}

    # ------------------------------------------------------------------ #
    # ACT
    # ------------------------------------------------------------------ #

    async def _act(self, decision: dict[str, Any], step: int) -> list[dict[str, Any]]:
        """Exécute les actions décidées."""
        actions = []

        if decision.get("type") == "tool_calls":
            for call in decision.get("calls", []):
                if self.tools_used >= self.tool_budget:
                    break
                action = await self._execute_tool_action(call)
                actions.append(action)
        elif decision.get("type") == "final":
            actions = decision.get("actions", [])
            for action in actions:
                result = await self._execute_explicit_action(action)
                actions.append(result)

        return actions

    async def _execute_tool_action(self, call: dict[str, Any]) -> dict[str, Any]:
        name = call.get("name")
        arguments = call.get("arguments", {})
        result = await self._tool_executor(name, arguments)
        return {"type": "tool_result", "tool": name, "result": result}

    async def _execute_explicit_action(self, action: dict[str, Any]) -> dict[str, Any]:
        atype = action.get("type")
        if atype == "create_commit":
            return await self._exec_commit(action)
        elif atype == "push_branch":
            return await self._exec_push(action)
        elif atype == "deploy_production":
            return await self._exec_deploy(action)
        elif atype == "tool_call":
            return await self._execute_tool_action(action)
        return {"type": "unknown", "action": action, "error": "Type d'action inconnu"}

    async def _exec_commit(self, action: dict[str, Any]) -> dict[str, Any]:
        confirmed = action.get("confirmed", False)
        if not confirmed:
            return {"type": "create_commit", "status": "awaiting_confirmation", "message": action.get("message")}
        # Exécution réelle via l'outil
        from app.services.development_agent.tools.git import create_commit
        from app.services.development_agent.tool_registry import ToolContext
        tool_ctx = self.ctx.tool_context()
        result = await create_commit(tool_ctx, {"message": action.get("message"), "add_all": True})
        if result.get("success"):
            self.ctx.task.commit_hash = result.get("commit_hash")
        return {"type": "create_commit", "status": "executed", **result}

    async def _exec_push(self, action: dict[str, Any]) -> dict[str, Any]:
        confirmed = action.get("confirmed", False)
        if not confirmed:
            return {"type": "push_branch", "status": "awaiting_confirmation"}
        from app.services.development_agent.tools.git import push_branch
        from app.services.development_agent.tool_registry import ToolContext
        tool_ctx = self.ctx.tool_context()
        result = await push_branch(tool_ctx, {"remote": action.get("remote", "origin")})
        self.ctx.task.push_status = "pushed" if result.get("success") else "failed"
        return {"type": "push_branch", "status": "executed", **result}

    async def _exec_deploy(self, action: dict[str, Any]) -> dict[str, Any]:
        confirmed = action.get("confirmed", False)
        if not confirmed:
            return {"type": "deploy_production", "status": "awaiting_confirmation"}
        from app.services.development_agent.tools.production import deploy_production
        from app.services.development_agent.tool_registry import ToolContext
        tool_ctx = self.ctx.tool_context()
        result = await deploy_production(tool_ctx, {"confirmed": True})
        self.ctx.task.deployment_status = "deployed" if result.get("success") else "failed"
        return {"type": "deploy_production", "status": "executed", **result}

    # ------------------------------------------------------------------ #
    # VERIFY
    # ------------------------------------------------------------------ #

    async def _verify(self, actions: list[dict[str, Any]], step: int) -> list[dict[str, Any]]:
        """Vérifie les résultats des actions (tests, diff, etc.)."""
        verifications = []
        for action in actions:
            if action.get("type") == "tool_result" and action.get("result", {}).get("success") is False:
                verifications.append({"action": action, "status": "failed", "error": action.get("result", {}).get("error")})
            elif action.get("type") == "create_commit" and action.get("status") == "executed":
                verifications.append({"action": action, "status": "committed", "commit_hash": action.get("commit_hash")})
            elif action.get("type") == "push_branch" and action.get("status") == "executed":
                verifications.append({"action": action, "status": "pushed"})
            elif action.get("type") == "deploy_production" and action.get("status") == "executed":
                verifications.append({"action": action, "status": "deployed"})
        return verifications

    def _reassess(self, decision: dict[str, Any], verifications: list[dict[str, Any]], step: int) -> bool:
        """Décide s'il faut continuer."""
        if decision.get("type") == "final":
            final_decision = decision.get("follow_up", False)
            return final_decision
        return True

    async def _record(self, phase: str, step: int, **kwargs) -> None:
        entry = {"phase": phase, "step": step, "timestamp": datetime.now(timezone.utc).isoformat(), **kwargs}
        # Réassignation obligatoire : SQLAlchemy ne détecte pas l'append
        # in-place sur une colonne JSON.
        steps = list(self.ctx.execution.steps_json or [])
        steps.append(entry)
        self.ctx.execution.steps_json = steps
        self.ctx.execution.step_count = step
        # Persistance immédiate : l'assistant affiche l'avancement en direct
        # pendant que l'agent tourne (requêtes /development/status concurrentes).
        try:
            await self.ctx.db.commit()
        except Exception:
            logger.warning("[DEV-AGENT] task=%s step persist failed", self.ctx.task.id, exc_info=True)
        logger.debug("[DEV-AGENT] task=%s step=%d phase=%s", self.ctx.task.id, step, phase)
