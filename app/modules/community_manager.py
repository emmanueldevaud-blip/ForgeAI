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
        items = []
        if "*" in permissions or "community_manager.strategy_view" in permissions:
            items.append({
                "code": self.info.code,
                "name": self.info.name,
                "icon": self.info.icon,
                "route": self.info.route_path,
                "order": self.info.order,
            })
        if "*" in permissions or "meta_analytics.view" in permissions:
            items.append({
                "code": f"{self.info.code}_analytics",
                "name": "Analytics & Intelligence",
                "icon": "bar-chart",
                "route": f"{self.info.route_path}/analytics",
                "order": self.info.order + 1,
            })
        return items

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True