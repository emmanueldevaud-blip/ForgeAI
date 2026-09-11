from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus, module_registry


class DashboardModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="dashboard",
            name="Tableau de bord",
            description="Vue d'ensemble et indicateurs clés",
            icon="dashboard",
            order=0,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/dashboard",
            component_path="Dashboard",
            required_permissions=["dashboard.view"],
            is_core=True,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class BuildingsModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="buildings",
            name="Bâtiments",
            description="Gestion des bâtiments et immeubles",
            icon="building",
            order=10,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/buildings",
            component_path="Buildings",
            required_permissions=["building.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions: list[str]):
        if self.info.required_permissions:
            if "*" in user_permissions:
                pass
            elif not all(p in user_permissions for p in self.info.required_permissions):
                return []

        children = [
            {
                "code": "buildings-sites",
                "name": "Sites",
                "icon": "building",
                "route": "/buildings",
                "order": 0,
            },
        ]

        has_manage_refs = (
            "*" in user_permissions
            or "building.manage_refs" in user_permissions
        )
        if has_manage_refs:
            children.append({
                "code": "buildings-refs",
                "name": "Référentiels",
                "icon": "file-text",
                "route": "/buildings/refs",
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

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class HousingModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="housing",
            name="Logements",
            description="Gestion des logements et appartements",
            icon="home",
            order=20,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/housing",
            component_path="Housing",
            required_permissions=["housing.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class MaintenanceModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="maintenance",
            name="Maintenance",
            description="Gestion des interventions de maintenance",
            icon="wrench",
            order=30,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/maintenance",
            component_path="Maintenance",
            required_permissions=["maintenance.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class CleaningModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="cleaning",
            name="Nettoyage",
            description="Gestion des prestations de nettoyage",
            icon="sparkles",
            order=40,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/cleaning",
            component_path="Cleaning",
            required_permissions=["cleaning.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class PeopleModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="people",
            name="Personnes",
            description="Gestion des personnes (locataires, propriétaires, contacts)",
            icon="users",
            order=50,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/people",
            component_path="People",
            required_permissions=["people.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class StudiesModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="studies",
            name="Études",
            description="Gestion des études techniques et diagnostics",
            icon="file-text",
            order=60,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/studies",
            component_path="Studies",
            required_permissions=["studies.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class SurveysModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="surveys",
            name="Métrés",
            description="Gestion des métrés et relevés",
            icon="ruler",
            order=70,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/surveys",
            component_path="Surveys",
            required_permissions=["surveys.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class QuotingModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="quoting",
            name="Chiffrage",
            description="Gestion des chiffrages et devis",
            icon="calculator",
            order=80,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/quoting",
            component_path="Quoting",
            required_permissions=["quoting.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class InventoryModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="inventory",
            name="Stocks",
            description="Gestion des stocks et inventaires",
            icon="package",
            order=90,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/inventory",
            component_path="Inventory",
            required_permissions=["inventory.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class PurchasingModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="purchasing",
            name="Achats",
            description="Gestion des achats et commandes",
            icon="shopping-cart",
            order=100,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/purchasing",
            component_path="Purchasing",
            required_permissions=["purchasing.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class SuppliersModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="suppliers",
            name="Fournisseurs",
            description="Gestion des fournisseurs et prestataires",
            icon="truck",
            order=110,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/suppliers",
            component_path="Suppliers",
            required_permissions=["suppliers.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class DocumentsModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="documents",
            name="Documents",
            description="Gestion documentaire et archives",
            icon="folder",
            order=120,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/documents",
            component_path="Documents",
            required_permissions=["documents.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class ReportsModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="reports",
            name="Rapports",
            description="Génération et consultation des rapports",
            icon="bar-chart",
            order=130,
            status=ModuleStatus.INACTIVE,
            version="1.0.0",
            route_path="/reports",
            component_path="Reports",
            required_permissions=["reports.view"],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class AdministrationModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="administration",
            name="Administration",
            description="Administration système et configuration",
            icon="settings",
            order=1000,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/administration",
            component_path="Administration",
            required_permissions=["admin.access"],
            is_core=True,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class TodoModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="todos",
            name="Tâches (Demo)",
            description="Module de démonstration - liste de tâches",
            icon="check-square",
            order=999,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/todos",
            component_path="Todos",
            required_permissions=[],
            is_core=False,
        ))

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


def register_all_modules():
    modules = [
        DashboardModule(),
        BuildingsModule(),
        HousingModule(),
        MaintenanceModule(),
        CleaningModule(),
        PeopleModule(),
        StudiesModule(),
        SurveysModule(),
        QuotingModule(),
        InventoryModule(),
        PurchasingModule(),
        SuppliersModule(),
        DocumentsModule(),
        ReportsModule(),
        AdministrationModule(),
        TodoModule(),
    ]
    for module in modules:
        module_registry.register(module)