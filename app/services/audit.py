from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

SENSITIVE_FIELDS = {
    "password",
    "password_hash",
    "new_password",
    "current_password",
    "old_password",
    "bind_password",
    "ad_bind_password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "jwt",
    "api_key",
    "private_key",
}


def sanitize_values(values: dict[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    sanitized = {}
    for key, value in values.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            sanitized[key] = "********"
        elif isinstance(value, datetime):
            sanitized[key] = value.isoformat()
        elif isinstance(value, dict):
            sanitized[key] = sanitize_values(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_values(v) if isinstance(v, dict) else (v.isoformat() if isinstance(v, datetime) else v)
                for v in value
            ]
        else:
            sanitized[key] = value
    return sanitized


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        *,
        action: str,
        module: str,
        user: User | None = None,
        username: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        object_repr: str | None = None,
        old_values: dict[str, Any] | None = None,
        new_values: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        status: str = "success",
        error_message: str | None = None,
    ) -> AuditLog:
        log_username = username or (user.__dict__.get("username", "anonymous") if user else "anonymous")
        log_user_id = user.__dict__.get("id") if user else None

        audit_log = AuditLog(
            user_id=log_user_id,
            username=log_username,
            action=action,
            module=module,
            object_type=object_type,
            object_id=object_id,
            object_repr=object_repr,
            old_values=sanitize_values(old_values),
            new_values=sanitize_values(new_values),
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            status=status,
            error_message=error_message,
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(audit_log)
        await self.db.flush()
        return audit_log

    async def get_logs(
        self,
        *,
        user_id: int | None = None,
        username: str | None = None,
        action: str | None = None,
        module: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLog]:
        query = select(AuditLog).order_by(AuditLog.created_at.desc())

        if user_id is not None:
            query = query.where(AuditLog.user_id == user_id)
        if username is not None:
            query = query.where(AuditLog.username == username)
        if action is not None:
            query = query.where(AuditLog.action == action)
        if module is not None:
            query = query.where(AuditLog.module == module)
        if object_type is not None:
            query = query.where(AuditLog.object_type == object_type)
        if object_id is not None:
            query = query.where(AuditLog.object_id == object_id)
        if status is not None:
            query = query.where(AuditLog.status == status)
        if start_date is not None:
            query = query.where(AuditLog.created_at >= start_date)
        if end_date is not None:
            query = query.where(AuditLog.created_at <= end_date)

        query = query.limit(limit).offset(offset)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_logs(
        self,
        *,
        user_id: int | None = None,
        username: str | None = None,
        action: str | None = None,
        module: str | None = None,
        object_type: str | None = None,
        object_id: str | None = None,
        status: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> int:
        from sqlalchemy import func
        query = select(func.count(AuditLog.id))

        if user_id is not None:
            query = query.where(AuditLog.user_id == user_id)
        if username is not None:
            query = query.where(AuditLog.username == username)
        if action is not None:
            query = query.where(AuditLog.action == action)
        if module is not None:
            query = query.where(AuditLog.module == module)
        if object_type is not None:
            query = query.where(AuditLog.object_type == object_type)
        if object_id is not None:
            query = query.where(AuditLog.object_id == object_id)
        if status is not None:
            query = query.where(AuditLog.status == status)
        if start_date is not None:
            query = query.where(AuditLog.created_at >= start_date)
        if end_date is not None:
            query = query.where(AuditLog.created_at <= end_date)

        result = await self.db.execute(query)
        return result.scalar_one()


async def get_audit_service(db: AsyncSession) -> AuditService:
    return AuditService(db)