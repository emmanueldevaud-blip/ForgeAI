from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus
from app.models.volunteer import Volunteer


class VolunteersModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="volunteers",
            name="Volontaires",
            description="Gestion des volontaires pour ménage et maintenance",
            icon="heart-handshake",
            order=25,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/volunteers",
            component_path="Volunteers",
            required_permissions=["volunteers.view"],
            is_core=False,
        ))

    async def install(self, db) -> bool:
        return True

    async def uninstall(self, db) -> bool:
        return True

    async def upgrade(self, db, from_version: str) -> bool:
        return True

    def get_navigation_items(self, user_permissions: list[str] | None = None):
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
            "children": [
                {
                    "code": "volunteers-list",
                    "name": "Liste des volontaires",
                    "icon": "users",
                    "route": "/volunteers",
                    "order": 0,
                },
                {
                    "code": "volunteers-create",
                    "name": "Créer un volontaire",
                    "icon": "plus",
                    "route": "/volunteers/create",
                    "order": 1,
                }
            ]
        }]
