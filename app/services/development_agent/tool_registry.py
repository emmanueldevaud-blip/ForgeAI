"""Registre d'outils de l'Agent Développement."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.rbac import RBACService

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Contexte d'exécution transmis aux outils."""

    db: AsyncSession
    user: User
    settings: Any
    task: "DevelopmentTask"
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def work_dir(self) -> str:
        return self.task.repository or "."


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]
    permission: str = "development.execute"
    access: str = "read"
    requires_confirmation: bool = False


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    requires_confirmation: bool = False

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"ok": self.ok}
        if self.ok:
            payload["data"] = self.data
        else:
            payload["error"] = self.error
        if self.requires_confirmation:
            payload["requires_confirmation"] = True
        return payload


class DevelopmentToolRegistry:
    """Ensemble des outils accessibles à l'Agent Développement."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Outil déjà enregistré : {spec.name}")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
                "access": spec.access,
            }
            for spec in sorted(self._tools.values(), key=lambda item: item.name)
        ]

    async def call(
        self,
        ctx: ToolContext,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        args = arguments or {}
        spec = self._tools.get(name)
        if spec is None:
            logger.warning("[DEV-AGENT] event=tool_denied name=%s reason=unknown", name)
            return ToolResult(ok=False, error=f"outil_inconnu:{name}")

        allowed = await self._has_permission(ctx, spec.permission)
        if not allowed:
            logger.warning(
                "[DEV-AGENT] event=tool_denied name=%s permission=%s user=%s",
                name,
                spec.permission,
                ctx.user.id,
            )
            return ToolResult(ok=False, error=f"permission_denied:{spec.permission}")

        if spec.requires_confirmation and not args.get("confirmed"):
            return ToolResult(ok=False, requires_confirmation=True, error="confirmation_requise")

        started = time.monotonic()
        try:
            data = await spec.handler(ctx, args)
        except Exception as exc:
            logger.exception("[DEV-AGENT] event=tool_failed name=%s access=%s", name, spec.access)
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {str(exc) or 'erreur'}")
        duration_ms = int((time.monotonic() - started) * 1000)
        logger.info(
            "[DEV-AGENT] event=tool_call name=%s access=%s ok=%s duration_ms=%d",
            name,
            spec.access,
            True,
            duration_ms,
        )
        return ToolResult(ok=True, data=data)

    @staticmethod
    async def _has_permission(ctx: ToolContext, permission: str) -> bool:
        if not permission:
            return True
        try:
            return await RBACService(ctx.db).user_has_permission(ctx.user, permission)
        except Exception:
            logger.exception(
                "[DEV-AGENT] event=tool_denied name=permission_check permission=%s",
                permission,
            )
            return False


@dataclass
class ToolCallRecord:
    name: str
    ok: bool
    arguments: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "ok": self.ok,
            "arguments": self.arguments,
            "duration_ms": self.duration_ms,
        }
        if self.error:
            payload["error"] = self.error
        return payload