from typing import Any

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user
from app.models import Module, ModuleConfig, ModuleStatus, User
from app.modules import module_registry
from app.services.audit import AuditService, get_audit_service


class ModuleService:
    def __init__(self, db: AsyncSession, audit: AuditService | None = None, current_user: User | None = None):
        self.db = db
        self.audit = audit
        self.current_user = current_user

    async def sync_modules(self) -> dict[str, Any]:
        registered_modules = module_registry.get_all()
        result = {
            "synced": 0,
            "created": 0,
            "updated": 0,
            "errors": [],
        }

        for reg_module in registered_modules:
            info = reg_module.info
            try:
                existing = await self.db.execute(
                    select(Module).where(Module.code == info.code)
                )
                module = existing.scalar_one_or_none()

                if module:
                    old_values = {
                        "name": module.name,
                        "description": module.description,
                        "icon": module.icon,
                        "order": module.order,
                        "status": module.status.value if hasattr(module.status, 'value') else module.status,
                        "version": module.version,
                        "route_path": module.route_path,
                        "component_path": module.component_path,
                        "required_permissions": module.required_permissions,
                        "settings": module.settings,
                        "is_core": module.is_core,
                        "dependencies": module.dependencies,
                    }
                    module.name = info.name
                    module.description = info.description
                    module.icon = info.icon
                    module.order = info.order
                    module.status = info.status
                    module.version = info.version
                    module.route_path = info.route_path
                    module.component_path = info.component_path
                    module.required_permissions = info.required_permissions
                    module.settings = info.settings
                    module.is_core = info.is_core
                    module.dependencies = info.dependencies
                    result["updated"] += 1

                    if self.audit:
                        new_values = {
                            "name": module.name,
                            "description": module.description,
                            "icon": module.icon,
                            "order": module.order,
                            "status": module.status.value if hasattr(module.status, 'value') else module.status,
                            "version": module.version,
                            "route_path": module.route_path,
                            "component_path": module.component_path,
                            "required_permissions": module.required_permissions,
                            "settings": module.settings,
                            "is_core": module.is_core,
                            "dependencies": module.dependencies,
                        }
                        await self.audit.log(
                            action="module_update",
                            module="modules",
                            user=self.current_user,
                            object_type="module",
                            object_id=str(module.id),
                            object_repr=module.code,
                            old_values=old_values,
                            new_values=new_values,
                            status="success",
                        )
                else:
                    module = Module(
                        code=info.code,
                        name=info.name,
                        description=info.description,
                        icon=info.icon,
                        order=info.order,
                        status=info.status,
                        version=info.version,
                        route_path=info.route_path,
                        component_path=info.component_path,
                        required_permissions=info.required_permissions,
                        settings=info.settings,
                        is_core=info.is_core,
                        dependencies=info.dependencies,
                    )
                    self.db.add(module)
                    result["created"] += 1

                    if self.audit:
                        await self.audit.log(
                            action="module_create",
                            module="modules",
                            user=self.current_user,
                            object_type="module",
                            object_id=info.code,
                            object_repr=info.code,
                            new_values={
                                "code": module.code,
                                "name": module.name,
                                "description": module.description,
                                "icon": module.icon,
                                "order": module.order,
                                "status": module.status.value if hasattr(module.status, 'value') else module.status,
                                "version": module.version,
                                "route_path": module.route_path,
                                "component_path": module.component_path,
                                "required_permissions": module.required_permissions,
                                "settings": module.settings,
                                "is_core": module.is_core,
                                "dependencies": module.dependencies,
                            },
                            status="success",
                        )

                result["synced"] += 1

            except Exception as e:
                result["errors"].append(f"Module {info.code}: {e!s}")

        await self.db.commit()
        return result

    async def get_module(self, code: str) -> Module | None:
        result = await self.db.execute(
            select(Module)
            .options(selectinload(Module.configs))
            .where(Module.code == code)
        )
        return result.scalar_one_or_none()

    async def get_all_modules(self) -> list[Module]:
        result = await self.db.execute(
            select(Module).order_by(Module.order)
        )
        return list(result.scalars().all())

    async def get_active_modules(self) -> list[Module]:
        result = await self.db.execute(
            select(Module)
            .where(Module.status == ModuleStatus.ACTIVE)
            .order_by(Module.order)
        )
        return list(result.scalars().all())

    async def enable_module(self, code: str) -> Module | None:
        module = await self.get_module(code)
        if module:
            old_status = module.status.value if hasattr(module.status, 'value') else module.status
            module.status = ModuleStatus.ACTIVE
            reg_module = module_registry.get(code)
            if reg_module:
                await reg_module.on_enable(self.db)
            await self.db.commit()
            await self.db.refresh(module)

            if self.audit:
                await self.audit.log(
                    action="module_enable",
                    module="modules",
                    user=self.current_user,
                    object_type="module",
                    object_id=str(module.id),
                    object_repr=module.code,
                    old_values={"status": old_status},
                    new_values={"status": "active"},
                    status="success",
                )
        return module

    async def disable_module(self, code: str) -> Module | None:
        module = await self.get_module(code)
        if module:
            old_status = module.status.value if hasattr(module.status, 'value') else module.status
            module.status = ModuleStatus.INACTIVE
            reg_module = module_registry.get(code)
            if reg_module:
                await reg_module.on_disable(self.db)
            await self.db.commit()
            await self.db.refresh(module)

            if self.audit:
                await self.audit.log(
                    action="module_disable",
                    module="modules",
                    user=self.current_user,
                    object_type="module",
                    object_id=str(module.id),
                    object_repr=module.code,
                    old_values={"status": old_status},
                    new_values={"status": "inactive"},
                    status="success",
                )
        return module

    async def update_module_config(self, module_code: str, configs: dict[str, Any]) -> Module:
        module = await self.get_module(module_code)
        if not module:
            raise ValueError(f"Module {module_code} not found")

        for key, value in configs.items():
            if isinstance(value, dict):
                config_key = key
                config_value = value.get("value")
                config_type = value.get("type", "string")
                config_description = value.get("description")
                config_is_secret = value.get("is_secret", False)
                config_is_required = value.get("is_required", False)
                config_validation = value.get("validation", {})
            else:
                config_key = key
                config_value = value
                config_type = "string"
                config_description = None
                config_is_secret = False
                config_is_required = False
                config_validation = {}

            existing = await self.db.execute(
                select(ModuleConfig).where(
                    ModuleConfig.module_id == module.id,
                    ModuleConfig.key == config_key
                )
            )
            config = existing.scalar_one_or_none()

            if config:
                old_values = {
                    "value": config.value,
                    "value_type": config.value_type,
                    "description": config.description,
                    "is_secret": config.is_secret,
                    "is_required": config.is_required,
                    "validation": config.validation,
                }
                config.value = str(config_value) if config_value is not None else None
                config.value_type = config_type
                if config_description:
                    config.description = config_description
                config.is_secret = config_is_secret
                config.is_required = config_is_required
                config.validation = config_validation

                new_values = {
                    "value": config.value,
                    "value_type": config.value_type,
                    "description": config.description,
                    "is_secret": config.is_secret,
                    "is_required": config.is_required,
                    "validation": config.validation,
                }

                if self.audit:
                    await self.audit.log(
                        action="module_config_update",
                        module="modules",
                        user=self.current_user,
                        object_type="module_config",
                        object_id=str(config.id),
                        object_repr=f"{module.code}.{config.key}",
                        old_values=old_values,
                        new_values=new_values,
                        status="success",
                    )
            else:
                config = ModuleConfig(
                    module_id=module.id,
                    key=config_key,
                    value=str(config_value) if config_value is not None else None,
                    value_type=config_type,
                    description=config_description,
                    is_secret=config_is_secret,
                    is_required=config_is_required,
                    validation=config_validation,
                )
                self.db.add(config)

                if self.audit:
                    await self.audit.log(
                        action="module_config_create",
                        module="modules",
                        user=self.current_user,
                        object_type="module_config",
                        object_id=f"{module.code}.{config_key}",
                        object_repr=f"{module.code}.{config_key}",
                        new_values={
                            "key": config.key,
                            "value": config.value,
                            "value_type": config.value_type,
                            "description": config.description,
                            "is_secret": config.is_secret,
                            "is_required": config.is_required,
                            "validation": config.validation,
                        },
                        status="success",
                    )

        await self.db.commit()
        await self.db.refresh(module)
        return module

    async def get_module_config(self, module_code: str) -> dict[str, Any]:
        module = await self.get_module(module_code)
        if not module:
            return {}

        config_dict = {}
        for config in module.configs:
            if config.is_secret:
                config_dict[config.key] = "********"
            else:
                config_dict[config.key] = config.value

        return config_dict

    async def get_module_with_registry(self, code: str) -> dict[str, Any] | None:
        db_module = await self.get_module(code)
        if not db_module:
            return None

        reg_module = module_registry.get(code)
        return {
            "db": db_module,
            "registry": reg_module,
            "navigation": reg_module.get_navigation_items([]) if reg_module else [],
        }

    async def install_module(self, code: str) -> bool:
        reg_module = module_registry.get(code)
        if not reg_module:
            return False

        db_module = await self.get_module(code)
        if not db_module:
            return False

        try:
            success = await reg_module.install(self.db)
            if success:
                old_status = db_module.status.value if hasattr(db_module.status, 'value') else db_module.status
                db_module.status = ModuleStatus.ACTIVE
                await self.db.commit()

                if self.audit:
                    await self.audit.log(
                        action="module_install",
                        module="modules",
                        user=self.current_user,
                        object_type="module",
                        object_id=str(db_module.id),
                        object_repr=db_module.code,
                        old_values={"status": old_status},
                        new_values={"status": "active"},
                        status="success",
                    )
            return success
        except Exception as e:
            db_module.status = ModuleStatus.ERROR
            await self.db.commit()

            if self.audit:
                await self.audit.log(
                    action="module_install",
                    module="modules",
                    user=self.current_user,
                    object_type="module",
                    object_id=str(db_module.id),
                    object_repr=db_module.code,
                    status="failure",
                    error_message=str(e),
                )
            return False

    async def uninstall_module(self, code: str) -> bool:
        if await self.is_core_module(code):
            return False

        reg_module = module_registry.get(code)
        if not reg_module:
            return False

        db_module = await self.get_module(code)
        if not db_module:
            return False

        try:
            success = await reg_module.uninstall(self.db)
            if success:
                old_status = db_module.status.value if hasattr(db_module.status, 'value') else db_module.status
                db_module.status = ModuleStatus.INACTIVE
                await self.db.commit()

                if self.audit:
                    await self.audit.log(
                        action="module_uninstall",
                        module="modules",
                        user=self.current_user,
                        object_type="module",
                        object_id=str(db_module.id),
                        object_repr=db_module.code,
                        old_values={"status": old_status},
                        new_values={"status": "inactive"},
                        status="success",
                    )
            return success
        except Exception as e:
            db_module.status = ModuleStatus.ERROR
            await self.db.commit()

            if self.audit:
                await self.audit.log(
                    action="module_uninstall",
                    module="modules",
                    user=self.current_user,
                    object_type="module",
                    object_id=str(db_module.id),
                    object_repr=db_module.code,
                    status="failure",
                    error_message=str(e),
                )
            return False

    async def is_core_module(self, code: str) -> bool:
        module = await self.get_module(code)
        return module.is_core if module else False


async def get_module_service(
    db: AsyncSession,
    current_user: User = Depends(get_current_active_user),
) -> ModuleService:
    audit = await get_audit_service(db)
    return ModuleService(db, audit=audit, current_user=current_user)