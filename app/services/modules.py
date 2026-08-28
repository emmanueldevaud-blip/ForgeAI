from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Module, ModuleConfig, ModuleStatus
from app.modules import module_registry, BaseModule


class ModuleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_modules(self) -> Dict[str, Any]:
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

                result["synced"] += 1

            except Exception as e:
                result["errors"].append(f"Module {info.code}: {str(e)}")

        await self.db.commit()
        return result

    async def get_module(self, code: str) -> Optional[Module]:
        result = await self.db.execute(
            select(Module)
            .options(selectinload(Module.configs))
            .where(Module.code == code)
        )
        return result.scalar_one_or_none()

    async def get_all_modules(self) -> List[Module]:
        result = await self.db.execute(
            select(Module).order_by(Module.order)
        )
        return list(result.scalars().all())

    async def get_active_modules(self) -> List[Module]:
        result = await self.db.execute(
            select(Module)
            .where(Module.status == ModuleStatus.ACTIVE)
            .order_by(Module.order)
        )
        return list(result.scalars().all())

    async def enable_module(self, code: str) -> Optional[Module]:
        module = await self.get_module(code)
        if module:
            module.status = ModuleStatus.ACTIVE
            reg_module = module_registry.get(code)
            if reg_module:
                await reg_module.on_enable(self.db)
            await self.db.commit()
            await self.db.refresh(module)
        return module

    async def disable_module(self, code: str) -> Optional[Module]:
        module = await self.get_module(code)
        if module:
            module.status = ModuleStatus.INACTIVE
            reg_module = module_registry.get(code)
            if reg_module:
                await reg_module.on_disable(self.db)
            await self.db.commit()
            await self.db.refresh(module)
        return module

    async def update_module_config(self, module_code: str, configs: Dict[str, Any]) -> Module:
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
                config.value = str(config_value) if config_value is not None else None
                config.value_type = config_type
                if config_description:
                    config.description = config_description
                config.is_secret = config_is_secret
                config.is_required = config_is_required
                config.validation = config_validation
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

        await self.db.commit()
        await self.db.refresh(module)
        return module

    async def get_module_config(self, module_code: str) -> Dict[str, Any]:
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

    async def get_module_with_registry(self, code: str) -> Optional[Dict[str, Any]]:
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
                db_module.status = ModuleStatus.ACTIVE
                await self.db.commit()
            return success
        except Exception:
            db_module.status = ModuleStatus.ERROR
            await self.db.commit()
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
                db_module.status = ModuleStatus.INACTIVE
                await self.db.commit()
            return success
        except Exception:
            db_module.status = ModuleStatus.ERROR
            await self.db.commit()
            return False

    async def is_core_module(self, code: str) -> bool:
        module = await self.get_module(code)
        return module.is_core if module else False


async def get_module_service(db: AsyncSession) -> ModuleService:
    return ModuleService(db)