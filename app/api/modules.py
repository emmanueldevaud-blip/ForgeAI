from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.api.deps import require_admin, require_permission
from app.services.modules import ModuleService, get_module_service
from app.modules import module_registry, register_all_modules
from app.models import Module, ModuleStatus
from app.services.rbac import RBACService
from app.services.audit import get_audit_service

router = APIRouter(prefix="/modules", tags=["modules"])


class ModuleConfigValue(BaseModel):
    value: Optional[str] = None
    type: str = "string"
    description: Optional[str] = None
    is_secret: bool = False
    is_required: bool = False
    validation: dict = {}


class ModuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: Optional[str]
    icon: Optional[str]
    order: int
    status: str
    version: str
    route_path: Optional[str]
    component_path: Optional[str]
    required_permissions: List[str]
    settings: dict
    is_core: bool
    dependencies: List[str]


class ModuleListResponse(BaseModel):
    modules: List[ModuleResponse]
    total: int


class ModuleConfigResponse(BaseModel):
    key: str
    value: Optional[str]
    value_type: str
    description: Optional[str]
    is_secret: bool
    is_required: bool
    validation: dict


class ModuleEnableRequest(BaseModel):
    action: str


async def require_module_access(
    current_user = Depends(require_permission("modules.view")),
    db: AsyncSession = Depends(get_db),
):
    return current_user


@router.get("", response_model=ModuleListResponse)
async def list_modules(
    current_user = Depends(require_permission("modules.view")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    modules = await service.get_all_modules()
    return ModuleListResponse(
        modules=[ModuleResponse.model_validate(m) for m in modules],
        total=len(modules)
    )


@router.get("/available", response_model=ModuleListResponse)
async def list_available_modules(
    current_user = Depends(require_permission("modules.view")),
    db: AsyncSession = Depends(get_db),
):
    rbac = RBACService(db)
    permissions = await rbac.get_user_permissions(current_user)
    service = await get_module_service(db)
    all_modules = await service.get_all_modules()
    available_modules = [
        m for m in all_modules
        if m.status == ModuleStatus.ACTIVE and (
            not m.required_permissions or all(p in permissions for p in m.required_permissions)
        )
    ]
    return ModuleListResponse(
        modules=[ModuleResponse.model_validate(m) for m in available_modules],
        total=len(available_modules)
    )


@router.get("/active", response_model=ModuleListResponse)
async def list_active_modules(
    current_user = Depends(require_module_access),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    modules = await service.get_active_modules()
    return ModuleListResponse(
        modules=[ModuleResponse.model_validate(m) for m in modules],
        total=len(modules)
    )


@router.get("/navigation")
async def get_navigation(
    current_user = Depends(require_module_access),
    db: AsyncSession = Depends(get_db),
):
    rbac = RBACService(db)
    permissions = await rbac.get_user_permissions(current_user)
    nav = module_registry.get_navigation(list(permissions))
    return {"navigation": nav}


@router.get("/{module_code}", response_model=ModuleResponse)
async def get_module(
    module_code: str,
    current_user = Depends(require_permission("modules.view")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    module = await service.get_module(module_code)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")
    return ModuleResponse.model_validate(module)


@router.post("/sync")
async def sync_modules(
    current_user = Depends(require_permission("modules.manage")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    result = await service.sync_modules()
    return result


@router.post("/{module_code}/enable")
async def enable_module(
    module_code: str,
    current_user = Depends(require_permission("modules.enable")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    module = await service.enable_module(module_code)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")
    return {"message": f"Module {module_code} activé", "module": ModuleResponse.model_validate(module)}


@router.post("/{module_code}/disable")
async def disable_module(
    module_code: str,
    current_user = Depends(require_permission("modules.disable")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    module = await service.disable_module(module_code)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")
    return {"message": f"Module {module_code} désactivé", "module": ModuleResponse.model_validate(module)}


@router.get("/{module_code}/config")
async def get_module_config(
    module_code: str,
    current_user = Depends(require_permission("modules.configure")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    config = await service.get_module_config(module_code)
    return {"module_code": module_code, "config": config}


@router.put("/{module_code}/config")
async def update_module_config(
    module_code: str,
    config: dict,
    current_user = Depends(require_permission("modules.configure")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    module = await service.update_module_config(module_code, config)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")
    return {"message": "Configuration mise à jour", "module_code": module_code}


@router.get("/{module_code}/permissions")
async def get_module_permissions(
    module_code: str,
    current_user = Depends(require_permission("modules.view")),
    db: AsyncSession = Depends(get_db),
):
    service = await get_module_service(db)
    module = await service.get_module(module_code)
    if not module:
        raise HTTPException(status_code=404, detail="Module non trouvé")

    reg_module = module_registry.get(module_code)
    permissions = reg_module.info.required_permissions if reg_module else []

    return {
        "module_code": module_code,
        "required_permissions": permissions,
        "db_required_permissions": module.required_permissions,
    }