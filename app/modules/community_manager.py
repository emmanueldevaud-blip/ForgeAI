"""Module Community Manager IA."""

from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus, module_registry


class CommunityManagerModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="community_manager",
            name="Community Manager IA",
            description="Stratégie éditoriale et génération de calendrier par IA",
            icon="megaphone",
            order=25,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/community-manager",
            component_path="CommunityManager",
            required_permissions=["community_manager.strategy_view"],
            is_core=False,
            dependencies=["sport"],
        ))

    def get_navigation_items(self, user_permissions=None):
        permissions = user_permissions or []
        if "*" not in permissions and "community_manager.strategy_view" not in permissions:
            return []
        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
        }]

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True