from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.admin import (
    AuditLogListParams,
    AuditLogListResponse,
    AuditLogResponse,
)
from app.services.audit import get_audit_service


router = APIRouter(
    prefix="/admin/audit-logs",
    tags=["admin-audit"]
)


class AuditFilterValuesResponse(BaseModel):
    modules: list[str]
    actions: list[str]
    usernames: list[str]


@router.get(
    "/filter-values",
    response_model=AuditFilterValuesResponse,
)
async def get_audit_filter_values(
    current_user: User = Depends(
        require_permission("audit_log_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)
    values = await audit.get_filter_values()
    return AuditFilterValuesResponse(**values)


@router.get(
    "",
    response_model=AuditLogListResponse
)
async def list_audit_logs(
    params: AuditLogListParams = Depends(),
    current_user: User = Depends(
        require_permission("audit_log_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    audit = await get_audit_service(db)

    offset = (params.page - 1) * params.page_size

    kwargs = {}
    if params.username:
        kwargs["username"] = params.username
    if params.action:
        kwargs["action"] = params.action
    if params.module:
        kwargs["module"] = params.module
    if params.object_type:
        kwargs["object_type"] = params.object_type
    if params.status:
        kwargs["status"] = params.status
    if params.start_date:
        kwargs["start_date"] = params.start_date
    if params.end_date:
        kwargs["end_date"] = params.end_date

    logs = await audit.get_logs(
        limit=params.page_size,
        offset=offset,
        **kwargs,
    )

    total = await audit.count_logs(**kwargs)

    total_pages = (
        (total + params.page_size - 1)
        // params.page_size
    )

    return AuditLogListResponse(
        logs=[
            AuditLogResponse.model_validate(
                log, from_attributes=True
            )
            for log in logs
        ],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{log_id}",
    response_model=AuditLogResponse
)
async def get_audit_log(
    log_id: int,
    current_user: User = Depends(
        require_permission("audit_log_view")
    ),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AuditLog).where(AuditLog.id == log_id)
    )

    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entrée d'audit non trouvée",
        )

    return AuditLogResponse.model_validate(
        log, from_attributes=True
    )
