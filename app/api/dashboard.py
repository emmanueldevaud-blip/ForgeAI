from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.services.dashboard import dashboard_registry
from app.services.rbac import RBACService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class WidgetMeta(BaseModel):
    id: str
    module: str
    title: str
    description: str
    permission: str
    widget_type: str
    width: str
    order: int
    link: str
    icon: str


class WidgetData(BaseModel):
    widget_id: str
    data: dict[str, Any]


@router.get("/widgets", response_model=list[WidgetMeta])
async def list_widgets(
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
):
    rbac = RBACService(db)
    permissions = await rbac.get_user_permissions(current_user)
    widgets = dashboard_registry.get_for_permissions(list(permissions))
    return [
        WidgetMeta(
            id=w.id,
            module=w.module,
            title=w.title,
            description=w.description,
            permission=w.permission,
            widget_type=w.widget_type,
            width=w.width,
            order=w.order,
            link=w.link,
            icon=w.icon,
        )
        for w in widgets
    ]


@router.get("/widgets/{widget_id}", response_model=WidgetData)
async def get_widget_data(
    widget_id: str,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
):
    widget = dashboard_registry.get_by_id(widget_id)
    if not widget:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Widget non trouvé")

    rbac = RBACService(db)
    has_perm = await rbac.user_has_permission(current_user, widget.permission)
    if not has_perm:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{widget.permission}' requise",
        )

    data = await widget.data_loader(db)
    return WidgetData(widget_id=widget_id, data=data)
