# Audit du projet ForgeAI

> Date : 2026-09-29 — Branche : `master` (`b90938f`)
> Nature du livrable : **constat et recommandations uniquement**. Aucune modification de code
> n'a été produite dans le cadre de cet audit.

---

## 1. Méthode

Ordre appliqué : **comprendre → reproduire → identifier la cause → corriger (non applicable ici) → vérifier → diff final**.

| Étape | Réalisé |
|---|---|
| Cartographie | inventaire complet des fichiers, lignes, routes, tables, tests |
| Syntaxe / build | `ast.parse` sur les 164 fichiers Python, `node --check` sur tous les JS |
| Backend | génération OpenAPI, extraction des 291 routes, analyse des dépendances de sécurité route par route |
| Frontend | extraction des appels API (`ApiClient`), recoupement systématique route par route avec le backend |
| Base de données | 1 Alembic head, 81 tables SQLAlchemy, `alembic check` |
| RBAC | catalogue de permissions seedé, codes vérifiés côté API et côté frontend |
| Config / environnement | `config.py` (61 settings) ↔ `.env` ↔ `.env.example`, Dockerfile, docker-compose |
| Tests | suite pytest complète |

Commandes de vérification (reproductibles) :

```bash
python3 -m compileall -q app tests alembic        # syntaxe (ici : ast.parse, 0 erreur)
node --check src/public/js/**/*.js                # syntaxe JS
.venv/bin/python -m pytest -q                     # 270 passed, 2 skipped
.venv/bin/python -m alembic heads                 # un seul head : 20260928_0030
```

---

## 2. Cartographie et chiffres

### 2.1 Backend (Python)

| Couche | Fichiers | Lignes |
|---|---:|---:|
| `app/api/` | 16 | 8 147 |
| `app/services/` | 35 | 15 502 |
| `app/schemas/` | 12 | 3 149 |
| `app/models/` | 17 | 2 557 |
| `app/core`, `app/db`, `app/modules`, `main.py` | 8 | 1 338 |
| `alembic/` (50 migrations) | 50 | 3 667 |
| `tests/` | 25 | 6 416 |
| **Total** | **164** | **41 078** |

### 2.2 Frontend (JS vanilla ES6, sans framework)

| Dossier | Fichiers | Lignes |
|---|---:|---:|
| `src/public/js/pages/` | 44 | 19 042 |
| `components/`, `router/`, `stores/` | 18 | 5 217 |
| `services/` (clients API) | 13 | 1 541 |
| `app-erp.js`, `app.js`, `verify-dashboard.js` | 3 | 1 827 |
| `src/public/css/` | 4 | 7 974 |

### 2.3 API

- **291 routes** (méthodes HTTP, hors HEAD/OPTIONS), **289 chemins distincts** → 2 doublons (§5.1).
- 16 routers montés dans `app/main.py:245-260`.
- **213 appels frontend** identifiés dans `src/public/js/services/` → **aucun appel orphelin**
  (chaque appel frontend correspond à une route backend réelle).

### 2.4 Base de données

- 81 tables SQLAlchemy, 50 migrations Alembic, **un seul head** : `20260928_0030`.
- Base de production : MySQL 8.4 via `asyncmy` (`docker-compose.yml`).
- Base locale utilisée par les tests : SQLite (`aiosqlite`).

### 2.5 Modules métier

Auth/AD, RBAC, Administration, Buildings, Equipment, Maintenance, Housing (hébergements,
ménage, occupations, emails), Volunteers, Administrative programs, Agenda, Sport,
Domotique (« La Cave »), Notifications (+ Web Push), Dashboard, Modules, Audit, AI Gateway.

### 2.6 Tests

272 tests collectés → **270 passed, 2 skipped** (les 2 skips = tests d'intégration MySQL,
`TEST_DATABASE_URL` non définie) en 6 min 37.

Couverture par domaine (nombre d'appels API exercés) : `buildings` 82, `auth` 35, `admin` 33,
`domotique` 21, `sport` 19, `notifications` 8, `agenda` 2, `modules` 1.
**Aucun test** sur : `housing`, `equipment`, `volunteers`, `administrative`, `maintenance`
(hors chat IA), `dashboard`, `audit`.

---

## 3. Constats de sécurité (priorité 1)

### S1 — CRITIQUE : routes `/volunteers/*` sans aucune authentification

`app/api/volunteer.py:15-90` — les 5 routes (`GET/POST /volunteers/`, `GET/PUT/DELETE
/volunteers/{id}`) ne déclarent que `Depends(get_db)`. Ni `get_current_active_user`, ni
`require_permission`. `get_current_active_user` est importé (ligne 5) mais jamais utilisé,
ce qui indique une intention non finalisée.

Conséquence : création, modification et suppression de volontaires **anonymement**, avec
audit log probablement vide (aucun utilisateur courant).

Comparez avec `app/api/administrative.py:19-26` (`service_for("administration.programs.view")`)
ou `app/api/housing.py:64-70` (`get_housing_service` → `require_permission("housing.view")`),
qui sont le modèle à suivre.

### S2 — HAUT : `cookies.txt` versionné dans le dépôt

`git ls-files` confirme que `cookies.txt` (fichier Netscape de cookies HTTP) est **tracké**.
Un fichier de cookies de session ne doit jamais être committé (règle « secrets »).

### S3 — HAUT : permissions référencées mais absentes du catalogue seedé

Le catalogue seedé se trouve dans `app/services/rbac.py:415-495` (`default_permissions`,
80 entrées). Les codes suivants sont utilisés par le code mais **n'existent pas** dans ce
catalogue (donc jamais insert en base, donc jamais attribuable à un rôle) :

| Code | Utilisé par | Effet |
|---|---|---|
| `permission_create` | `app/api/admin.py:1334` | 403 systématique |
| `permission_update` | `app/api/admin.py:1401` | 403 systématique |
| `permission_delete` | `app/api/admin.py:1451` | 403 systématique |
| `volunteers.manage` | `CleaningVolunteersPage.js:59,65` | boutons « Modifier/Supprimer » toujours désactivés |
| `housing.create` | `HousingUnavailabilitiesPage.js:166` | bouton « Nouvelle indisponibilité » masqué |
| `housing.delete` | `HousingUnavailabilitiesPage.js:82` | action « Supprimer » toujours désactivée |

`seed_default_rbac` n'attribue aux rôles `admin`/`super_admin` que les permissions
**existentes** (`app/services/rbac.py:513-517`), et aucun droit `*` n'est jamais créé
(`app/services/rbac.py:42` teste `"*" in permissions`, mais aucune ligne de ce type n'est
seedée). Vérification faite sur la base de test locale : 25 permissions présentes, **aucune**
des 6 codes ci-dessus.

Note : si `PermissionsPage.js` permet de créer des permissions, elle-même exige
`permission_create` → **impasse** (voir S4).

### S4 — HAUT : `require_admin` et `require_super_admin` sont identiques

`app/api/deps.py:62-81` : les deux dépendances ne vérifient que la permission `user_view`.
`require_super_admin` n'est d'ailleurs utilisé nulle part.

Conséquence : tout utilisateur disposant de `user_view` passe pour les routes
`/auth/users*` (`app/api/auth.py:386, 402, 417, 445, 465, 489`), alors que les routes
équivalentes `/admin/users*` sont protégées par des permissions plus précises.
Il existe deux implémentations concurrentes de la gestion des utilisateurs
(`/auth/users` et `/admin/users`).

### S5 — MOYEN : rate limiting configuré mais jamais appliqué

`slowapi` est instancié (`app/main.py:30`) et branché (`app/main.py:202`), avec un handler
d'exception. **Aucun décorateur `@limiter.limit` n'existe** dans le dépôt. `/auth/login`
et `/auth/refresh` ne sont donc protégés par aucun quota (force brute).

---

## 4. Constats RBAC / cohérence des permissions

Inventaire : **80 permissions** dans le catalogue, **62 codes** utilisés via
`require_permission(...)` côté API, **41 codes** utilisés côté frontend.

### 4.1 Permissions du catalogue jamais vérifiées par le backend (17)

`admin.access`, `administration.programs.{configure,manage,validate,view}` (couvert par
`service_for`, OK), `dashboard.view`, `documents.view`, `domotique.access`, `domotique.admin`,
`maintenance.{create,update,delete,execute,plan,view_costs,manage}`, `sport.admin`,
`volunteers.view`.

Points notables :
- `dashboard.view` existe mais `/dashboard/widgets*` n'impose que l'authentification
  (`app/api/dashboard.py`, 0 `require_permission`).
- `maintenance.create/update/delete/execute` existent, alors que l'API n'impose que
  `maintenance.view` + `maintenance.manage_*` (`app/api/maintenance.py:85-277`).
  Le frontend, lui, contrôle les boutons avec `maintenance.create` / `maintenance.update`
  (7 et 6 occurrences) → **un utilisateur autorisé par l'API peut ne pas voir le bouton**,
  ou l'inverse selon l'affectation des rôles.

### 4.2 Codes frontend sans équivalent backend

En dehors des 3 de S3 : `housing.create`, `housing.delete`, `volunteers.manage`.
Les autres « codes » détectés côté frontend sont des libellés de KPI
(`housing.occupied`, `equipment.total`, `maintenance.open_requests`, …) et non des
permissions — à ne pas confondre lors d'une correction.

### 4.3 Routes sans garde de permission (25 sur 291)

- **`/volunteers/*` (5)** → voir S1, problème réel.
- `/auth/*` (login, logout, refresh, me, register, settings, change_password) → attendu.
- `/housing/public/cleaning-invitations/{token}` → lien public délibéré.
- `/notifications/*` (9) → délibéré et documenté (`app/api/notifications.py:1-4`) :
  chaque route est bien filtrée par `current_user.id` (vérifié sur `list_notifications`
  et `mark_read`) → **pas d'IDOR**.
- `/dashboard/widgets*` (2), `/modules/navigation` (1) → authentification seule (§4.1).

---

## 5. Constats de fiabilité / architecture

### 5.1 Doublons de routes Housing (moyen)

`app/api/housing.py` :
- `POST /housing/occupancies` définie **2 fois** : lignes 294 et 753
- `PATCH /housing/occupancies/{occupancy_id}` définie **2 fois** : lignes 322 et 761

Les deux blocs sont identiques. FastAPI ne garde que la première définition : le second est
**du code mort**, et la génération OpenAPI émet deux avertissements de
*Duplicate Operation ID* (`create_occupancy`, `update_occupancy`).

### 5.2 Code mort frontend (faible)

Fichiers trackés mais jamais chargés (`index.html` ne charge que `app-erp.js`) :

- `src/public/js/app.js` (1 700 lignes, contient un `fetch` maison en parallèle du client API)
- `src/public/js/verify-dashboard.js`
- `src/public/css/style.css` (non référencé dans `index.html`)
- `src/public/js/pages/HousingUnavailabilitiesPage.js` → **la route backend
  `/housing/unavailabilities` existe, mais aucune page n'est montée pour l'exposer**,
  alors que le reste du module Housing est atteignable via `HousingPage.js`.

### 5.3 Dette technique

- 74 `TODO/FIXME/HACK` (5 backend, 69 frontend) ; 35 `console.log` résiduels.
- Cache-busting manuel par query string (`?v=50`) dans les imports de `app-erp.js` :
  à chaque modification de page, la version doit être incrémentée à la main.
- `docker-compose.override.yml` (non tracké, présent localement) force
  `DOMOTIQUE_ENABLED=false` et `DOMOTIQUE_POLL_INTERVAL_S=0` — utile en dev,
  **à ne pas commettre tel quel** s'il doit rester local.
- Fichiers de développement résiduels à la racine : `server.log`, `forgeai.db`,
  `database.db` (vides), `test_forgeai.db` — déjà couverts par `.gitignore`, sauf
  `cookies.txt` (voir S2).
- `Dockerfile` ne copie que `app/`, `alembic/`, `alembic.ini` : **`src/public` n'est pas
  dans l'image**. Le frontend doit être monté en volume par la compose de production
  (à confirmer avant toute modification du déploiement).
- Tests d'intégration MySQL skippés par défaut : le comportement réel MySQL (asyncmy,
  contraintes, index) n'est pas exercé dans la boucle de test courante.

### 5.4 Ce qui est sain

- 0 erreur de syntaxe Python et JavaScript sur l'intégralité du dépôt.
- Frontend ↔ backend : **0 appel API orphelin** sur 213 appels.
- Un seul head Alembic, migrations datées et séquentielles, 81 tables cohérentes.
- `config.py` / `.env` / `.env.example` : 61 settings, aucune clé manquante
  (seules les valeurs par défaut d'options optionnelles sont absentes de `.env`).
- Aucun secret en dur détecté dans le code source (scan `password/secret/api_key = "..."`).
- Auth : JWT avec expiration (30 min / refresh 7 j), `passlib` en `bcrypt_sha256`,
  accept du token via cookie ou header.
- Notifications : filtrage systématique par utilisateur, doc explicite de l'absence de
  permission RBAC.
- Pattern de garde homogène sur Housing / Administrative / Agenda / Buildings / Equipment /
  Domotique (usines de services avec `require_permission`).

---

## 6. Top 10 des priorités

| # | Priorité | Référence | Effort estimé |
|---|---|---|---|
| 1 | Fermer l'accès anonyme sur `/volunteers/*` (S1) | `app/api/volunteer.py` | faible |
| 2 | Retirer `cookies.txt` du suivi git + l'ajouter au `.gitignore` (S2) | racine | faible |
| 3 | Aligner `require_admin`/`require_super_admin` sur des permissions réelles (S4) | `app/api/deps.py:62-81` | faible |
| 4 | Ajouter `permission_create/update/delete`, `volunteers.manage`, `housing.create`, `housing.delete` au catalogue seedé **ou** corriger les appels (S3) | `app/services/rbac.py:415-495` | faible |
| 5 | Appliquer `@limiter.limit` sur `/auth/login` et `/auth/refresh` (S5) | `app/api/auth.py` | faible |
| 6 | Supprimer les 2 définitions dupliquées d'occupancies (5.1) | `app/api/housing.py:753,761` | faible |
| 7 | Décider de l'arbitrage FE/BE sur `maintenance.create` et consorts (4.1) | `app/api/maintenance.py`, pages Maintenance | moyen |
| 8 | Découper la double implémentation `/auth/users` vs `/admin/users` (S4) | `app/api/auth.py:386+` | moyen |
| 9 | Nettoyer le code mort frontend et décider du sort de `HousingUnavailabilitiesPage` (5.2) | `src/public/` | moyen |
| 10 | Ajouter des tests sur `housing`, `equipment`, `volunteers` (2.6) | `tests/` | moyen |

---

## 7. Portée et limites de cet audit

- **Aucune modification** de code, de configuration ou de base de données n'a été effectuée.
  `git status` ne montre que `docker-compose.override.yml` (non tracké, non modifié ici).
- La base MySQL de production n'a pas été interrogée : `alembic check` a été exécuté sur la
  base SQLite locale et signale un décalage (`Target database is not up to date`), ce qui
  **ne préjuge pas** de l'état de la base MySQL de production.
- Aucun test d'intrusion, aucun profiling de performance, aucune vérification des
  dépendances obsolètes.
- Les tests verts (270) ne constituent **pas** une preuve de bon fonctionnement : ils ne
  couvrent pas Housing, Equipment, Volunteers, Administrative, Maintenance (hors IA),
  Dashboard ni Audit.
