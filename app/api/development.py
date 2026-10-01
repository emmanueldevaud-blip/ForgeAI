"""Endpoints HTTP de l'Agent Développement (statut Git, commit, déploiement).

Ces routes sont des adaptateurs fins : elles déléguent exclusivement aux
outils et services déjà présents dans ``app.services.development_agent``
(registre d'outils Git / production, service de tâches).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.config import get_settings
from app.db.session import get_db
from app.models.development import DevelopmentTask
from app.models.user import User
from app.services.development_agent.service import DevelopmentService
from app.services.development_agent.tool_registry import ToolContext, ToolResult
from app.services.development_agent.tools import build_registry
from app.services.development_agent.tools.reading import get_repository_status

router = APIRouter(prefix="/development", tags=["development"])


class CommitRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    confirmed: bool = False


class DeployRequest(BaseModel):
    confirmed: bool = False


def _tool_context(db: AsyncSession, user: User) -> ToolContext:
    settings = get_settings()
    task = DevelopmentTask(repository=settings.OPENCODE_WORK_DIR or ".")
    return ToolContext(db=db, user=user, settings=settings, task=task)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _task_payload(task: DevelopmentTask) -> dict:
    status_value = task.status.value if hasattr(task.status, "value") else str(task.status)
    return {
        "id": task.id,
        "title": task.title,
        "status": status_value,
        "branch": task.branch,
        "error": task.error,
        "commit_hash": task.commit_hash,
        "push_status": task.push_status,
        "deployment_status": task.deployment_status,
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def _tool_response(result: ToolResult) -> dict:
    if not result.ok:
        if result.requires_confirmation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Confirmation requise pour cette action",
            )
        error = result.error or "Action refusée"
        if error.startswith("permission_denied"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

    data = result.data if isinstance(result.data, dict) else {"result": result.data}
    if data.get("error") and not data.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(data["error"]))
    return data


@router.get("/status")
async def development_status(
    current_user: User = Depends(require_permission("development.view")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    git = await get_repository_status(_tool_context(db, current_user), {})
    tasks = await DevelopmentService(db, current_user).list_tasks(limit=1)
    return {
        "git": git,
        "task": _task_payload(tasks[0]) if tasks else None,
    }


@router.post("/commit")
async def development_commit(
    data: CommitRequest,
    current_user: User = Depends(require_permission("development.commit")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await build_registry().call(
        _tool_context(db, current_user),
        "create_commit",
        {"message": data.message, "confirmed": data.confirmed},
    )
    return _tool_response(result)


@router.post("/deploy")
async def development_deploy(
    data: DeployRequest,
    current_user: User = Depends(require_permission("development.deploy")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await build_registry().call(
        _tool_context(db, current_user),
        "deploy_production",
        {"confirmed": data.confirmed},
    )
    return _tool_response(result)
