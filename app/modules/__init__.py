from app.core.module_registry import BaseModule, ModuleInfo, ModuleStatus, module_registry
from app.modules.agenda import AgendaModule
from app.modules.domotique import DomotiqueModule
from app.modules.photos import PhotosModule
from app.modules.sport import SportModule


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


class GestionBureauxModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="gestion_bureaux",
            name="Intendance",
            description="Gestion des bâtiments, hébergements et équipements",
            icon="building",
            order=30,
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
                "name": "Bâtiments",
                "icon": "building",
                "route": "/buildings",
                "order": 0,
            },
        ]

        has_equipment = (
            "*" in user_permissions
            or "equipment.view" in user_permissions
        )
        if has_equipment:
            children.append({
                "code": "equipment-list",
                "name": "Équipements",
                "icon": "tool",
                "route": "/equipment",
                "order": 1,
            })

        has_housing = (
            "*" in user_permissions
            or "housing.view" in user_permissions
        )
        if has_housing:
            children.append({
                "code": "housing-list",
                "name": "Hébergements",
                "icon": "home",
                "route": "/housing",
                "order": 2,
            })

        has_volunteers = (
            "*" in user_permissions
            or "volunteers.view" in user_permissions
        )
        if has_volunteers:
            children.append({
                "code": "volunteers-list",
                "name": "Volontaires",
                "icon": "heart-handshake",
                "route": "/volunteers",
                "order": 3,
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


class BuildingsModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="buildings",
            name="Bâtiments",
            description="Gestion des bâtiments et immeubles",
            icon="building",
            order=30,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/buildings",
            component_path="Buildings",
            required_permissions=["building.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions: list[str]):
        return []

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
            name="Hébergements",
            description="Gestion des hébergements, occupations et ménage",
            icon="home",
            order=50,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/housing",
            component_path="Housing",
            required_permissions=["housing.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions=None):
        return []

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
            description="GMAO - Gestion de Maintenance Assistée par Ordinateur",
            icon="wrench",
            order=60,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/maintenance",
            component_path="Maintenance",
            required_permissions=["maintenance.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions=None):
        children = [
            {
                "code": "maintenance-requests",
                "name": "Demandes",
                "icon": "inbox",
                "route": "/maintenance/requests",
                "order": 0,
            },
            {
                "code": "maintenance-work-orders",
                "name": "Ordres de travail",
                "icon": "clipboard",
                "route": "/maintenance/work-orders",
                "order": 1,
            },
            {
                "code": "maintenance-preventive",
                "name": "Préventif",
                "icon": "calendar-check",
                "route": "/maintenance/preventive",
                "order": 2,
            },
            {
                "code": "maintenance-calendar",
                "name": "Calendrier",
                "icon": "calendar",
                "route": "/maintenance/calendar",
                "order": 3,
            },
        ]

        if user_permissions and (
            "maintenance.manage_providers" in user_permissions
            or "*" in user_permissions
        ):
            children.append({
                "code": "maintenance-providers",
                "name": "Prestataires",
                "icon": "users",
                "route": "/maintenance/providers",
                "order": 4,
            })

        if user_permissions and (
            "maintenance.manage_contracts" in user_permissions
            or "*" in user_permissions
        ):
            children.append({
                "code": "maintenance-contracts",
                "name": "Contrats",
                "icon": "file-text",
                "route": "/maintenance/contracts",
                "order": 5,
            })

        if user_permissions and (
            "maintenance.manage_referentials" in user_permissions
            or "*" in user_permissions
        ):
            children.append({
                "code": "maintenance-refs",
                "name": "Référentiels",
                "icon": "database",
                "route": "/maintenance/refs",
                "order": 6,
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
            code="parametres_generaux",
            name="Paramètres généraux",
            description="Administration système et configuration",
            icon="settings",
            order=1000,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/parametres-generaux",
            component_path="Administration",
            required_permissions=["admin.access"],
            is_core=True,
        ))

    def get_navigation_items(self, user_permissions=None):
        permissions = user_permissions or []
        if "*" not in permissions and "admin.access" not in permissions:
            return []
        children = []
        general_children = [
            ("administration-users", "Utilisateurs", "users", "/administration/users", "user_view"),
            ("administration-groups", "Groupes", "users", "/administration/groups", "group_view"),
            ("administration-roles", "Rôles", "shield", "/administration/roles", "role_view"),
            ("administration-permissions", "Permissions", "lock", "/administration/permissions", "permission_view"),
            ("administration-audit", "Audit", "clipboard", "/administration/audit", "audit_log_view"),
            ("administration-ad", "Active Directory", "database", "/administration/active-directory", "ad_config"),
            ("administration-smtp", "E-mail / SMTP", "mail", "/administration/smtp", "settings_view"),
            ("administration-ai", "Assistant IA", "bot", "/administration/ai", "settings_view"),
        ]
        for code, name, icon, route, permission in general_children:
            if "*" in permissions or permission in permissions:
                children.append({"code": code, "name": name, "icon": icon, "route": route, "order": len(children)})
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


class AdministrativeProgramsModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="administratif",
            name="Administratif",
            description="Gestion des programmes des volontaires",
            icon="calendar",
            order=10,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/administratif",
            component_path="AdministrativePrograms",
            required_permissions=["administration.programs.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions=None):
        permissions = user_permissions or []
        if "*" not in permissions and "administration.programs.view" not in permissions:
            return []
        return [{
            "code": self.info.code,
            "name": self.info.name,
            "icon": self.info.icon,
            "route": self.info.route_path,
            "order": self.info.order,
            "children": [{
                "code": "administratif-programs",
                "name": "Programmes",
                "icon": "calendar",
                "route": "/administratif/programs",
                "order": 0,
            }],
        }]

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class EquipmentModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="equipment",
            name="Équipements",
            description="Gestion du patrimoine des équipements",
            icon="tool",
            order=40,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/equipment",
            component_path="Equipment",
            required_permissions=["equipment.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions: list[str]):
        return []

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


class AIModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="ai_assistant",
            name="Assistant IA",
            description="Assistant intelligent transverse",
            icon="bot",
            order=20,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/ai",
            component_path="AIAssistant",
            required_permissions=["ai.use"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions=None):
        if user_permissions and (
            "ai.use" in user_permissions
            or "*" in user_permissions
        ):
            return [{
                "code": self.info.code,
                "name": self.info.name,
                "icon": self.info.icon,
                "route": self.info.route_path,
                "order": self.info.order,
            }]
        return []

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True


def register_all_modules():
    modules = [
        DashboardModule(),
        GestionBureauxModule(),
        BuildingsModule(),
        EquipmentModule(),
        HousingModule(),
        MaintenanceModule(),
        AgendaModule(),
        VolunteersModule(),
        AIModule(),
        CleaningModule(),
        PeopleModule(),
        StudiesModule(),
        SurveysModule(),
        QuotingModule(),
        InventoryModule(),
        PurchasingModule(),
        SportModule(),
        DomotiqueModule(),
        PhotosModule(),
        SuppliersModule(),
        DocumentsModule(),
        ReportsModule(),
        AdministrationModule(),
        AdministrativeProgramsModule(),
    ]
    for module in modules:
        module_registry.register(module)

class VolunteersModule(BaseModule):
    def __init__(self):
        super().__init__(ModuleInfo(
            code="volunteers",
            name="Volontaires",
            description="Gestion des volontaires pour ménage et maintenance",
            icon="heart-handshake",
            order=80,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/volunteers",
            component_path="Volunteers",
            required_permissions=["volunteers.view"],
            is_core=False,
        ))

    def get_navigation_items(self, user_permissions=None):
        return []

    async def install(self, db):
        return True

    async def uninstall(self, db):
        return True

    async def upgrade(self, db, from_version: str):
        return True

# Register all modules at import time to ensure they are available
# regardless of lifespan/startup handler execution
from app.modules import register_all_modules
register_all_modules()
