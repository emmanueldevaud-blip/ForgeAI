from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus


class DomotiqueModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="domotique",
            name="Domotique",
            description="Supervision des installations domotiques (la cave)",
            icon="thermometer",
            order=75,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/domotique",
            component_path="Domotique",
            required_permissions=["domotique.access"],
            is_core=False,
        ))

    async def install(self, db) -> bool:
        return True

    async def uninstall(self, db) -> bool:
        return True

    async def upgrade(self, db, from_version: str) -> bool:
        return True

    def get_navigation_items(self, user_permissions: list[str] | None = None):
        permissions = user_permissions or []
        if "domotique.access" not in permissions and "*" not in permissions:
            return []

        children = []
        if "*" in permissions or "domotique.view" in permissions:
            children.append({
                "code": "domotique-sechoir",
                "name": "La Cave",
                "icon": "thermometer",
                "route": "/domotique",
                "order": 0,
            })

        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
            "children": children,
        }]
