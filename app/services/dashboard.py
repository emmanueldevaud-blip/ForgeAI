from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable


@dataclass
class WidgetDefinition:
    id: str
    module: str
    title: str
    description: str
    permission: str
    widget_type: str  # "counter" | "alert" | "list" | "table"
    width: str  # "sm" | "md" | "lg"
    order: int
    data_loader: Callable[..., Awaitable[dict[str, Any]]]
    link: str = ""
    icon: str = ""


class DashboardWidgetRegistry:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._widgets: dict[str, WidgetDefinition] = {}
        return cls._instance

    def register(self, widget: WidgetDefinition):
        self._widgets[widget.id] = widget

    def get_all(self) -> list[WidgetDefinition]:
        return sorted(self._widgets.values(), key=lambda w: (w.module, w.order))

    def get_by_id(self, widget_id: str) -> WidgetDefinition | None:
        return self._widgets.get(widget_id)

    def get_for_permissions(self, permissions: list[str]) -> list[WidgetDefinition]:
        result = []
        for widget in self.get_all():
            if "*" in permissions or widget.permission in permissions:
                result.append(widget)
        return result

    def get_modules(self, permissions: list[str]) -> dict[str, list[WidgetDefinition]]:
        widgets = self.get_for_permissions(permissions)
        modules: dict[str, list[WidgetDefinition]] = {}
        for w in widgets:
            modules.setdefault(w.module, []).append(w)
        return modules


dashboard_registry = DashboardWidgetRegistry()


def register_dashboard_widgets():
    from app.services.dashboard_widgets import register_all_widget_providers
    register_all_widget_providers()
