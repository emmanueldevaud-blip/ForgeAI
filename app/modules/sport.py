from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus
from app.models.rbac import Permission


class SportModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="sport",
            name="Sport",
            description="Module de suivi d'activités sportives (course, trail, ultra)",
            icon="run",
            order=100,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/sport",
            component_path="Sport",
            required_permissions=["sport.access"],
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

        has_activities = (
            user_permissions and
            ("*" in user_permissions or
             "sport.activities.read" in user_permissions)
        )
        has_goals = (
            user_permissions and
            ("*" in user_permissions or
             "sport.goals.read" in user_permissions)
        )

        children = []

        if has_activities:
            children.append({
                "code": "sport-activities",
                "name": "Activités",
                "icon": "run",
                "route": "/sport/activities",
                "order": 0,
            })

        if has_goals:
            children.append({
                "code": "sport-goals",
                "name": "Objectifs",
                "icon": "target",
                "route": "/sport/goals",
                "order": 1,
            })

        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
            "children": children,
        }]