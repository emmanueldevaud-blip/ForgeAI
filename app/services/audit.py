from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import AuditLog, User
from app.core.config import get_settings


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


def sanitize_values(values: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if values is None:
        return None
    sanitized = {}
    for key, value in values.items():
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            sanitized[key] = "********"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_values(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_values(v) if isinstance(v, dict) else v
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
        user: Optional[User] = None,
        username: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        object_repr: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> AuditLog:
        log_username = username or (user.username if user else "anonymous")
        log_user_id = user.id if user else None

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
            created_at=datetime.now(),
        )

        self.db.add(audit_log)
        await self.db.flush()
        return audit_log

    async def get_logs(
        self,
        *,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        action: Optional[str] = None,
        module: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditLog]:
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
        user_id: Optional[int] = None,
        username: Optional[str] = None,
        action: Optional[str] = None,
        module: Optional[str] = None,
        object_type: Optional[str] = None,
        object_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
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