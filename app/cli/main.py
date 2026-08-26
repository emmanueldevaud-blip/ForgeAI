import asyncio
import getpass
import sys
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, init_db
from app.services.auth import create_user, hash_password
from app.models.user import User, UserRole
from app.core.config import get_settings


async def create_admin(
    username: str,
    email: str,
    password: str,
    first_name: str = "",
    last_name: str = "",
) -> User:
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Utilisateur '{username}' existe déjà", file=sys.stderr)
            sys.exit(1)

        result = await db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            print(f"Email '{email}' déjà utilisé", file=sys.stderr)
            sys.exit(1)

        user = await create_user(db, {
            "username": username,
            "email": email,
            "first_name": first_name or None,
            "last_name": last_name or None,
            "password": password,
            "is_active": True,
            "is_admin": True,
            "role": UserRole.ADMIN,
            "source": "local",
        })
        return user


async def interactive_create_admin():
    print("=== Création du premier administrateur ===\n")

    username = input("Nom d'utilisateur: ").strip()
    if not username:
        print("Nom d'utilisateur requis", file=sys.stderr)
        sys.exit(1)

    email = input("Email: ").strip()
    if not email:
        print("Email requis", file=sys.stderr)
        sys.exit(1)

    while True:
        password = getpass.getpass("Mot de passe (min 8 caractères): ")
        if len(password) < 8:
            print("Le mot de passe doit faire au moins 8 caractères")
            continue
        confirm = getpass.getpass("Confirmer le mot de passe: ")
        if password != confirm:
            print("Les mots de passe ne correspondent pas")
            continue
        break

    first_name = input("Prénom (optionnel): ").strip() or None
    last_name = input("Nom (optionnel): ").strip() or None

    print("\nCréation de l'administrateur...")
    await init_db()
    user = await create_admin(username, email, password, first_name or "", last_name or "")
    print(f"\n✓ Administrateur créé avec succès !")
    print(f"  ID: {user.id}")
    print(f"  Username: {user.username}")
    print(f"  Email: {user.email}")
    print(f"  Rôle: {user.role.value}")


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


if __name__ == "__main__":
    main()