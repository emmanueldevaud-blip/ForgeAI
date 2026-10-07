from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus


class AgendaModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="agenda",
            name="Agenda",
            description="Présences dans les locaux Bureau et occupation des postes de travail",
            icon="calendar-check",
            order=25,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/agenda",
            component_path="Agenda",
            required_permissions=["agenda.access"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions: list[str] | None = None):
        permissions = user_permissions or []
        if "*" not in permissions and "agenda.access" not in permissions:
            return []
        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
            "children": [
                {
                    "code": "agenda-mine",
                    "name": "Ma présence",
                    "icon": "user",
                    "route": "/agenda?tab=mine",
                    "order": 0,
                },
                {
                    "code": "agenda-inscriptions",
                    "name": "Inscriptions",
                    "icon": "calendar-check",
                    "route": "/agenda?tab=inscriptions",
                    "order": 1,
                },
                {
                    "code": "agenda-settings",
                    "name": "Paramètres",
                    "icon": "settings",
                    "route": "/agenda?tab=settings",
                    "order": 2,
                    "required_permissions": ["agenda.manage"],
                },
            ],
        }]

    async def install(self, db) -> bool:
        return True

    async def uninstall(self, db) -> bool:
        return True

    async def upgrade(self, db, from_version: str) -> bool:
        return True
