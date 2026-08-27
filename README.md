# ForgeAI Demo Application

Application web de démonstration complète avec authentification (locale + Active Directory).

## Architecture

- **Backend**: FastAPI (Python 3.11+) avec SQLAlchemy 2.0 (async)
- **Frontend**: Vanilla JavaScript (ES6+), HTML5, CSS3
- **Base de données**: MySQL 8.4 (production) / SQLite (tests)
- **Authentification**: JWT (access + refresh tokens) + cookies HttpOnly sécurisés
- **Migrations**: Alembic
- **Tests**: pytest + httpx (async)

## Fonctionnalités d'authentification

### Authentification Locale
- Inscription / Connexion avec email + mot de passe
- Hashage bcrypt (rounds configurables)
- Gestion des rôles: `user`, `admin`
- Création du premier admin via CLI interactif

### Authentification Active Directory (LDAP/LDAPS)
- Bind avec compte de service
- Recherche utilisateur par `sAMAccountName`
- Vérification mot de passe via bind utilisateur
- Récupération groupes et mapping vers rôles application
- Ne stocke **jamais** le mot de passe AD en base

### Sécurité
- Tokens JWT à durée limitée (access: 30min, refresh: 7j)
- Cookies HttpOnly, Secure, SameSite=Lax
- Pas de fuite d'info sur l'existence des comptes
- Rate limiting configurable
- Secrets via variables d'environnement uniquement
- CORS restreint au frontend

### Autorisation
- Dépendances FastAPI: `require_auth`, `require_admin`
- Système de rôles extensible
- Interface d'administration pour gestion utilisateurs

## Installation

### Prérequis
- Python 3.11+
- MySQL 8.4 (ou Docker)

### Configuration

```bash
cp .env.example .env
# Éditer .env avec vos valeurs
```

Variables requises:
- `SECRET_KEY`: Clé secrète JWT (générer avec `openssl rand -hex 32`)
- `DATABASE_URL`: URL MySQL (ex: `mysql://user:pass@localhost:3306/forgeai`)

### Avec Docker (recommandé)

```bash
docker-compose up -d
```

### Installation manuelle

```bash
# Backend
python -m venv venv
source venv/bin/activate
pip install -e .

# Base de données
alembic upgrade head

# Créer le premier admin
python -m app.cli create-admin

# Lancer le serveur
uvicorn app.main:app --reload --port 8000
```

Le frontend est servi automatiquement sur `http://localhost:8000`

## Commandes utiles

```bash
# Migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# Tests
pytest -v
pytest --cov=app --cov-report=html

# CLI Admin
python -m app.cli create-admin
python -m app.cli create-admin --non-interactive --username admin --email admin@test.com --password secret123

# Linting
ruff check .
mypy app/
```

## Structure du projet

```
forgeai/
├── app/
│   ├── api/           # Routes API (auth, todos)
│   ├── cli/           # Commandes CLI (create-admin)
│   ├── core/          # Configuration, sécurité
│   ├── db/            # Session DB, modèles de base
│   ├── models/        # Modèles SQLAlchemy (User, Todo)
│   ├── schemas/       # Schémas Pydantic (request/response)
│   ├── services/      # Logique métier (auth, LDAP)
│   └── main.py        # Application FastAPI
├── alembic/           # Migrations
├── src/public/        # Frontend vanilla JS
├── tests/             # Tests unitaires et d'intégration
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

## API Endpoints

### Authentification
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| POST | `/auth/login` | Connexion (local + AD) |
| POST | `/auth/logout` | Déconnexion |
| POST | `/auth/refresh` | Rafraîchir access token |
| GET | `/auth/me` | Utilisateur courant |
| POST | `/auth/register` | Inscription locale |
| GET | `/auth/settings` | Config auth (AD enabled, etc.) |

### Administration (admin requis)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/auth/users` | Lister utilisateurs |
| POST | `/auth/users` | Créer utilisateur |
| PATCH | `/auth/users/{id}` | Modifier utilisateur |
| POST | `/auth/users/{id}/reset-password` | Reset mot de passe |
| DELETE | `/auth/users/{id}` | Supprimer utilisateur |

### Todos (auth requis)
| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/api/todos` | Lister tous les todos |
| POST | `/api/todos` | Créer todo |
| GET | `/api/todos/{id}` | Détail todo |
| PATCH | `/api/todos/{id}` | Modifier todo |
| DELETE | `/api/todos/{id}` | Supprimer todo |

## Configuration Active Directory

Variables d'environnement pour l'AD:

```env
AD_ENABLED=true
AD_SERVER=ad.mondomaine.com
AD_PORT=636
AD_USE_SSL=true
AD_BASE_DN=DC=mondomaine,DC=com
AD_USER_DN=OU=Users,DC=mondomaine,DC=com
AD_USER_SEARCH_FILTER=(sAMAccountName={username})
AD_GROUP_SEARCH_BASE=OU=Groups,DC=mondomaine,DC=com
AD_ADMIN_GROUP=CN=AppAdmins,OU=Groups,DC=mondomaine,DC=com
AD_BIND_USER=CN=svc_forgeai,OU=ServiceAccounts,DC=mondomaine,DC=com
AD_BIND_PASSWORD=mot_de_passe_du_compte_service
AD_GROUP_MAPPING={"admin": "AppAdmins", "user": "AppUsers"}
```

### Mapping des groupes AD
- `AD_GROUP_MAPPING`: JSON mapping groupe AD → rôle application
- Par défaut: `AppAdmins` → `admin`, `AppUsers` → `user`
- L'utilisateur est créé/mis à jour en base lors de la 1ère connexion AD

## Tests

```bash
# Tous les tests
pytest

# Avec couverture
pytest --cov=app --cov-report=term-missing

# Tests spécifiques
pytest tests/test_auth.py::TestPasswordHashing -v
pytest tests/test_auth.py::TestLocalAuthentication -v
pytest tests/test_auth.py::TestAuthorization -v
```

## Déploiement Production

1. Générer `SECRET_KEY` fort: `openssl rand -hex 32`
2. Configurer MySQL 8.4 avec charset `utf8mb4`
3. Définir `DEBUG=false`
4. Configurer `CORS_ORIGINS` pour votre domaine
5. Activer `AD_ENABLED=true` et configurer LDAPS
6. Utiliser un reverse proxy (nginx) avec TLS
7. Configurer les cookies `Secure=true`

## Licence

MIT