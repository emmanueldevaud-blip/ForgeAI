from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.models.module import ModuleStatus


@dataclass
class ModuleInfo:
    code: str
    name: str
    description: str = ""
    icon: str = ""
    order: int = 0
    status: ModuleStatus = ModuleStatus.INACTIVE
    version: str = "1.0.0"
    route_path: str = ""
    component_path: str = ""
    required_permissions: list[str] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    is_core: bool = False
    dependencies: list[str] = field(default_factory=list)


class BaseModule(ABC):
    def __init__(self, info: ModuleInfo):
        self.info = info

    @abstractmethod
    async def install(self, db) -> bool:
        pass

    @abstractmethod
    async def uninstall(self, db) -> bool:
        pass

    @abstractmethod
    async def upgrade(self, db, from_version: str) -> bool:
        pass

    async def on_enable(self, db) -> bool:
        return True

    async def on_disable(self, db) -> bool:
        return True

    def get_routes(self):
        return []

    def get_frontend_routes(self):
        return []

    def get_permissions(self):
        return self.info.required_permissions

    def get_navigation_items(self, user_permissions: list[str]):
        if self.info.required_permissions:
            if "*" in user_permissions:
                pass
            elif not all(p in user_permissions for p in self.info.required_permissions):
                return []
        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
        }]


class ModuleRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._modules: dict[str, BaseModule] = {}
        return cls._instance

    def register(self, module: BaseModule):
        self._modules[module.info.code] = module

    def unregister(self, code: str):
        if code in self._modules:
            del self._modules[code]

    def get(self, code: str) -> BaseModule | None:
        return self._modules.get(code)

    def get_all(self) -> list[BaseModule]:
        return list(self._modules.values())

    def get_active(self) -> list[BaseModule]:
        return [m for m in self._modules.values() if m.info.status == ModuleStatus.ACTIVE]

    def get_ordered_active(self) -> list[BaseModule]:
        return sorted(self.get_active(), key=lambda m: m.info.order)

    def get_navigation(self, user_permissions: list[str]) -> list[dict[str, Any]]:
        nav_items = []
        for module in self.get_ordered_active():
            items = module.get_navigation_items(user_permissions)
            nav_items.extend(items)
        return nav_items


module_registry = ModuleRegistry()