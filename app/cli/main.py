import asyncio
import getpass
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, init_db
from app.services.auth import create_user, hash_password
from app.services.rbac import RBACService
from app.models.user import User, UserRole
from app.models.rbac import Role, PermissionModel, Permission, Group, RolePermission
from app.core.config import get_settings


DEFAULT_PERMISSIONS = [
    # Dashboard
    ("dashboard.view", "Voir le tableau de bord", "dashboard"),
    # Buildings
    ("buildings.view", "Voir les bâtiments", "buildings"),
    ("buildings.create", "Créer des bâtiments", "buildings"),
    ("buildings.update", "Modifier des bâtiments", "buildings"),
    ("buildings.delete", "Supprimer des bâtiments", "buildings"),
    # Maintenance
    ("maintenance.view", "Voir la maintenance", "maintenance"),
    ("maintenance.create", "Créer des interventions", "maintenance"),
    ("maintenance.update", "Modifier des interventions", "maintenance"),
    ("maintenance.delete", "Supprimer des interventions", "maintenance"),
    # Users
    ("users.view", "Voir les utilisateurs", "users"),
    ("users.create", "Créer des utilisateurs", "users"),
    ("users.update", "Modifier des utilisateurs", "users"),
    ("users.delete", "Supprimer des utilisateurs", "users"),
    ("users.manage_roles", "Gérer les rôles utilisateurs", "users"),
    # Groups
    ("groups.view", "Voir les groupes", "groups"),
    ("groups.create", "Créer des groupes", "groups"),
    ("groups.update", "Modifier des groupes", "groups"),
    ("groups.delete", "Supprimer des groupes", "groups"),
    ("groups.manage_members", "Gérer les membres des groupes", "groups"),
    # Roles
    ("roles.view", "Voir les rôles", "roles"),
    ("roles.create", "Créer des rôles", "roles"),
    ("roles.update", "Modifier des rôles", "roles"),
    ("roles.delete", "Supprimer des rôles", "roles"),
    ("roles.manage_permissions", "Gérer les permissions des rôles", "roles"),
    # Modules
    ("modules.view", "Voir les modules", "modules"),
    ("modules.enable", "Activer des modules", "modules"),
    ("modules.disable", "Désactiver des modules", "modules"),
    ("modules.configure", "Configurer des modules", "modules"),
    # AD
    ("ad.view", "Voir la configuration AD", "ad"),
    ("ad.config", "Configurer l'AD", "ad"),
    ("ad.sync", "Synchroniser l'AD", "ad"),
    ("ad.test", "Tester la connexion AD", "ad"),
    # Audit
    ("audit.view", "Voir les logs d'audit", "audit"),
    # Settings
    ("settings.view", "Voir les paramètres", "settings"),
    ("settings.update", "Modifier les paramètres", "settings"),
]


DEFAULT_ROLES = [
    {
        "code": "super_admin",
        "name": "Super Administrateur",
        "description": "Accès complet à toutes les fonctionnalités",
        "is_system": True,
        "permissions": [p[0] for p in DEFAULT_PERMISSIONS],
    },
    {
        "code": "admin",
        "name": "Administrateur",
        "description": "Administration du système et gestion des utilisateurs",
        "is_system": True,
        "permissions": [
            "dashboard.view",
            "users.view", "users.create", "users.update", "users.manage_roles",
            "groups.view", "groups.create", "groups.update", "groups.manage_members",
            "roles.view", "roles.create", "roles.update", "roles.manage_permissions",
            "modules.view", "modules.enable", "modules.disable", "modules.configure",
            "ad.view", "ad.config", "ad.sync", "ad.test",
            "audit.view",
            "settings.view", "settings.update",
        ],
    },
    {
        "code": "user",
        "name": "Utilisateur",
        "description": "Accès standard aux modules activés",
        "is_system": True,
        "permissions": [
            "dashboard.view",
        ],
    },
]


async def seed_rbac(db: AsyncSession) -> dict:
    rbac = RBACService(db)
    result = {
        "permissions_created": 0,
        "permissions_existing": 0,
        "roles_created": 0,
        "roles_existing": 0,
        "role_permissions_created": 0,
    }

    for perm_code, perm_name, perm_module in DEFAULT_PERMISSIONS:
        existing = await rbac.get_permission_by_code(perm_code)
        if existing:
            result["permissions_existing"] += 1
            continue
        await rbac.create_permission(
            code=perm_code,
            name=perm_name,
            module=perm_module,
            is_system=True,
        )
        result["permissions_created"] += 1

    for role_data in DEFAULT_ROLES:
        existing = await rbac.get_role_by_code(role_data["code"])
        if existing:
            result["roles_existing"] += 1
            role = existing
        else:
            role = await rbac.create_role(
                code=role_data["code"],
                name=role_data["name"],
                description=role_data["description"],
                is_system=role_data["is_system"],
            )
            result["roles_created"] += 1

        for perm_code in role_data["permissions"]:
            perm = await rbac.get_permission_by_code(perm_code)
            if perm:
                existing_rp = await db.execute(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id
                    )
                )
                if not existing_rp.scalar_one_or_none():
                    await rbac.assign_permission_to_role(role.id, perm.id)
                    result["role_permissions_created"] += 1

    return result


async def seed_command():
    print("=== Initialisation RBAC (rôles et permissions par défaut) ===\n")
    await init_db()
    
    async with AsyncSessionLocal() as db:
        print("Création des permissions...")
        result = await seed_rbac(db)
        print(f"\n✓ Initialisation RBAC terminée !")
        print(f"  Permissions créées: {result['permissions_created']}")
        print(f"  Permissions existantes: {result['permissions_existing']}")
        print(f"  Rôles créés: {result['roles_created']}")
        print(f"  Rôles existants: {result['roles_existing']}")
        print(f"  Affectations rôle-permission créées: {result['role_permissions_created']}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Commandes CLI ForgeAI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_admin_parser = subparsers.add_parser("create-admin", help="Créer le premier administrateur")
    create_admin_parser.add_argument("--username", help="Nom d'utilisateur")
    create_admin_parser.add_argument("--email", help="Email")
    create_admin_parser.add_argument("--password", help="Mot de passe (non recommandé, utilisez le mode interactif)")
    create_admin_parser.add_argument("--first-name", default="", help="Prénom")
    create_admin_parser.add_argument("--last-name", default="", help="Nom")
    create_admin_parser.add_argument("--non-interactive", action="store_true", help="Mode non interactif")

    seed_parser = subparsers.add_parser("seed", help="Initialiser les rôles et permissions par défaut")

    args = parser.parse_args()

    if args.command == "create-admin":
        if args.non_interactive:
            if not all([args.username, args.email, args.password]):
                print("En mode non-interactif, --username, --email et --password sont requis", file=sys.stderr)
                sys.exit(1)
            asyncio.run(create_admin(args.username, args.email, args.password, args.first_name, args.last_name))
            print(f"Administrateur '{args.username}' créé")
        else:
            asyncio.run(interactive_create_admin())
    elif args.command == "seed":
        asyncio.run(seed_command())


if __name__ == "__main__":
    main()