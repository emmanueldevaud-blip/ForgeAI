# Module Photos

Gestionnaire de photos auto-hébergé (inspiré d'Apple Photos) pour ForgeAI.
Les originaux ne sont jamais modifiés : toute retouche crée une nouvelle version.

## Fonctionnalités

### Opérationnelles (MVP)

- **Import** : multipart multiple, détection d'image (Pillow), garde sur la taille
  max (`PHOTO_MAX_UPLOAD_SIZE`), empreinte SHA-256 pour le diagnostic de doublons.
- **Pipeline d'arrière-plan** (table persistante `photo_jobs`, pattern identique à
  `DevelopmentTask`) :
  `IMPORT → THUMBNAILS → METADATA → PHOTO_ANALYSIS → EMBEDDING → INDEXATION`.
  Un job `running` orphelin (processus mort) est remis en file après 15 min.
  Aucune étape ne bloque l'upload ni l'affichage de la galerie.
- **Score de qualité** (`PHOTO_QUALITY_ENABLED`) : netteté (variance du
  laplacien), flou (densité de contours), exposition, cadrage — calculé en
  Python pur sur une miniature, stocké dans `photo_analyses.result_json.quality`.
- **Embeddings & photos similaires** (`PHOTO_EMBEDDING_ENABLED`) : vecteur
  image par photo (provider local `local_grid`, 768 dims), recherche par
  similarité cosinus `GET /photos/{id}/similar`, ré-indexation
  `POST /photos/{id}/embeddings`.
- **Galerie** : grille lazy (`loading="lazy"`), scroll infini par curseur opaque
  (valeur du champ de tri + `id`), filtres favoris / album / personne / lieu,
  recherche textuelle, pastille d'état de l'analyse IA par tuile.
- **Recherche naturelle** : heuristique FR/EN (stop-words + reconnaissance
  d'entités : personnes, tags, lieux) combinée au texte libre restant
  (`free_text` sur titre, fichier, appareil, tags **et** lieux) ;
  optionnellement enrichie par l'AI Gateway (`PHOTO_AI_SEARCH_ENABLED=true`).
  Le moteur de recherche reste déterministe : aucune génération SQL par LLM.
  Section « Recherche intelligente » (suggestions) dans la barre d'outils.
- **Albums** : création, renommage, suppression, ajout/retrait de photos.
- **Personnes / visages (V2)** : détection locale des visages, groupes
  anonymes auto (« Personne N »), regroupement par similarité cosinus,
  renommage / fusion / séparation, couverture par groupe, recadrage privé,
  affectation manuelle (`PATCH /photos/faces/{id}`).
- **Tags** : ajout/retrait manuel par photo, tags générés par l'analyse.
- **Lieux** : cache de cellules GPS arrondies (0,01°), compteur de photos.
- **Retouche** : rotation, recadrage, réglages, amélioration automatique —
  versions cumulatives rendues depuis l'original (`GET /photos/{id}/edits/{eid}/file`),
  retour à l'original (`POST /photos/{id}/revert`).
- **Suppression logique** (`is_deleted`) + restauration.
- **Doublons** : groupes par hash de contenu (`GET /photos/duplicates`).
- **Sécurité** : privé par défaut (scopé `owner_id`), `photos.manage_all` pour
  l'accès transverse, fichiers servis uniquement après permission `photos.view`.

### Préparées (non branchées)

- **Analyseur vision `llm_vision`** : réservé — l'AI Gateway actuelle
  n'accepte que du texte (`gateway.generate(prompt=…)`, aucune entrée image).
  Le branchement se fera sans toucher au gateway (interface
  `PhotoAnalysisProvider` déjà en place), activation locale par défaut.
- **Géocodage inverse** : `PhotoPlace.label` reste vide sans appel externe
  (`PHOTO_GEOCODING_ENABLED` réservé).
- **Opérations IA de retouche** (`ai_remove`, `ai_upscale`) : répondent `501`
  (sortie réservée à une évolution).
- **Outils développeur** : `app/services/photo/tools.py` expose 9 outils du type
  `development_agent` (recherche, analyse, albums…).

## Analyse & indexation (V1)

### Providers d'analyse

`PhotoAnalysisProvider` (protocol dans `app/services/photo/analysis.py`) —
contrat `name` / `model` / `version` + `analyze(photo, image_path)` :

| Provider | Rôle |
|---|---|
| `metadata` (actif) | Tags objectifs locaux (portrait/paysage, nuit, GPS, appareil), sans modèle |
| `local_vision` | Classification locale — à ajouter dans `_ANALYZERS` |
| `llm_vision` | Vision via l'AI Gateway — réservé (voir ci-dessus) |

- Une seule ligne `photo_analyses` par photo (ré-utilisée à chaque
  ré-analyse) : la table sert d'état d'indexation
  (`provider`, `model`, `version`, `status`, `completed_at`), pas d'historique.
- Changer `PHOTO_ANALYZER` (ou la version du provider) provoque une
  ré-analyse au prochain job ; un échec est consigné puis **rejoué** avec
  backoff (le job `analyze` lève `PhotoJobError` → `max_attempts`).
- Tous les résultats (tags + `result_json` : dimensions, nuit, qualité)
  sont écrits par le job : jamais dans le chemin de requête HTTP.

### Embeddings & stockage vectoriel

- Interface `EmbeddingProvider` (`app/services/photo/embeddings.py`) :
  `name` / `model` / `version` / `dimensions` + `embed_image(path)` —
  découplée du provider d'analyse (on peut changer l'un sans l'autre).
- Provider par défaut `local_grid` : grille 16×16 RGB aplatie (768 dims),
  normalisée L2 — 100 % local, déterministe, aucune dépendance ajoutée.
- **Stockage** : table `photo_embeddings` (PK `photo_id`), vecteur sérialisé
  en JSON **dans la base applicative**. Choix justifié : MySQL 8.4 n'a pas de
  type vector, et une base vectorielle (pgvector, Milvus…) est démesurée pour
  une photothèque personnelle. Le cosinus est calculé en Python sur les
  vecteurs du propriétaire (repli portable SQLite/MySQL).
- **Ré-indexation** : la ligne est réécrite si `provider`/`model`/`version`
  changent ; `POST /photos/{id}/embeddings` force le recalcul (bouton
  « Ré-indexer » du visionneuse). Un job déjà en file est réutilisé
  (anti-doublons), jamais doublonné.
- **Similarité** : `GET /photos/{id}/similar?limit=12` → vecteurs les plus
  proches (cosinus), scopés `owner_id`, photos supprimées exclues ;
  `indexed: false` si la photo source n'est pas encore indexée.

### Confidentialité

Le chemin par défaut est **local-first** : `metadata` + `local_grid` ne
sortent aucun octet du serveur. Aucun appel externe n'est activé par défaut
(`PHOTO_AI_SEARCH_ENABLED` pour la reformulation de requête reste un appel
texte optionnel, `PHOTO_GEOCODING_ENABLED=false`).

## Visages & personnes (V2)

### Détection (local-first)

- Protocol `FaceDetectionProvider` (`app/services/photo/face_detection.py`) :
  `name` / `model` / `version` / `dimensions` + `detect(image_path)` — registre
  `register_face_detector` / `get_face_detector`, sélectionné par
  `PHOTO_FACE_DETECTOR`.
- Moteur actif `LocalFaceDetector` (`local_heuristic`, `skin-blob-v1`) :
  heuristique « teinte de peau » + composantes connexes sur la miniature
  configurée, embedding = vignette 8×8 (192 dims, L2). 100 % local,
  déterministe, sans dépendance — remplaçable (Haar, DNN…) sans toucher ni
  aux jobs ni aux tables.
- L'état est une ligne `photo_analyses` **kind = "faces"** (provider / model /
  version / status / error) : un changement de détecteur ou de version
  déclenche la ré-indexation (`POST /photos/{id}/faces`, bouton
  « Détecter visages » de la visionneuse). La ré-détection remplace les
  visages de la photo (les couvertures referençant d'anciens visages sont
  neutralisées) ; maximum 8 visages par photo.
- Jamais l'original : détection et recadrages travaillent sur les miniatures.

### Regroupement (`face_grouping.py`)

- Comparaison aux **centroïdes** des groupes (O(n·k)), pas d'all-vs-all ;
  `FaceIndex` abstrait la recherche top-k (`FlatFaceIndex` en force brute,
  remplaçable par FAISS / MySQL VECTOR sans changer l'algorithme).
- Seuls les groupes **anonymes** (« Personne N ») sont créés/rejoints
  automatiquement : un groupe nommé par l'utilisateur ne l'est jamais.
- Seuils : `PHOTO_FACE_GROUP_THRESHOLD=0.90` (affectation),
  `PHOTO_FACE_GROUP_MERGE_THRESHOLD=0.97` (fusion d'anonymes, bornée à
  10 tours). Fusion / renommage / séparation restent des actions explicites.
- La couverture manquante d'un groupe est le premier visage (id minimal).
- Les groupes anonymes vides sont purgés ; les groupes nommés sont conservés.

### API personnes / visages

| Endpoint | Rôle |
|---|---|
| `GET/POST /photos/people` | Liste (compteurs dynamiques) / création |
| `GET/PATCH/DELETE /photos/people/{id}` | Détail / renommage **et couverture** (`cover_face_id`) / suppression (désassocie les visages) |
| `GET /photos/people/{id}/faces` | Visages du groupe (cadrages) |
| `POST /photos/people/{id}/merge` | Fusion : la route porte la **cible**, le corps la **source** |
| `PATCH /photos/faces/{id}` | Affectation à un groupe (`person_id`) |
| `POST /photos/faces/{id}/unassign` | Séparation du groupe (groupe anonyme vide → purgé) |
| `GET /photos/faces/{id}/crop?size=` | JPEG recadré privé (`Cache-Control: private`), miniature uniquement |
| `POST /photos/{id}/faces` | Détection / ré-indexation forcée (jobs `face_detect` → `face_embedding`) |

### Confidentialité des visages

Les embeddings et les visages sont des **données sensibles** : scopés
`owner_id`, servis uniquement avec `photos.view` (crops : propriétaire ou
`photos.manage_all`), jamais transmis à l'extérieur — aucun provider externe
n'est branché. La suppression d'une photo neutralise immédiatement ses
visages dans tous les compteurs, la recherche et le regroupement.

## Stockage & import NAS (V3)

### Abstraction de stockage

Les **originaux** (source de vérité) sont délégués à un
`PhotoStorageBackend` (`app/services/photo/storage.py`) :

| Backend | Racine des originaux | Comportement |
|---|---|---|
| `local` (défaut) | `PHOTO_STORAGE_PATH/originals` | Comportement historique inchangé |
| `nas` | `PHOTO_NAS_PATH` | Répertoire **déjà monté par le système** — ForgeAI n'ouvre aucune connexion SMB/NFS |

- Miniatures et versions retouchées restent **toujours locales** (cache
  rapide, indépendant du NAS).
- Chaque photo porte une colonne `storage_backend` : la **lecture suit la
  photo, jamais la configuration courante** — changer le backend ne rend
  jamais une photo existante inaccessible (et un backend retiré de la
  configuration donne un 404 propre, pas un 500).
- Arborescence et noms de fichiers restent identiques ; les chemins en
  base restent relatifs (anti path traversal : `..`, absolu, `\`,
  caractères de contrôle refusés ; espaces/accents des photothèques
  réelles acceptés).
- **Les originaux NAS ne sont jamais supprimés** par ForgeAI :
  `delete_original` y est un no-op explicite (journalisé), y compris sur
  un échec d'import ; la suppression d'une photo reste logique
  (`is_deleted`), le fichier est laissé en place.

### Scan / import idempotent

`POST /photos/import/scan` (permission `photos.upload`) enfile un job
`scan_import` (photo_id nul) — **jamais bloquant** côté HTTP. Le handler
exécute `app/services/photo/scan.py::run_scan` :

- parcours progressif (`os.walk` + lots SQL, sans tout charger en
  mémoire), sous-répertoires et accents gérés, symlinks ignorés ;
- extensions : formats uploadés + `heic/heif` + `mov/mp4` ;
- **idempotent** : un fichier déjà référencé (même `storage_path`) est
  ignoré sans recalcul de hash ;
- **dédup** : SHA-256 streamé (octets identiques à l'upload) par
  `(owner, backend)` — un exemplaire en double est ignoré, un fichier
  déplacé/renommé (ancien chemin disparu) fait **mis à jour** le
  `storage_path` sans création ;
- nouvelles photos : même chaîne `ingest` qu'un upload (EXIF, miniatures,
  analyse, visages) — un `PhotoScanRun` persiste l'état (fichiers vus,
  créés, déplacés, manquants) affiché dans l'UI.

**Garanties de sécurité** : le stockage est `check`-é avant (`available`
/ `unavailable` / `error` : absent, non dir, illisible, ou vide alors
qu'un montage est attendu) et **après** le parcours. Un état non
`available` interrompt tout : le marquage « manquants » (suppression
logique réversible, aucun fichier touché) n'a lieu qu'après un scan
complet avec stockage `available` au début **et** à la fin. Jamais de
suppression massive en cas de monture absente.

### Vidéos & HEIC (limitations documentées)

- `mp4`/`mov` : **référencés** (mime correct, `status=ready`) mais sans
  miniatures ni analyse image — le décodage vidéo reste hors périmètre V3
  (`analysis_status=skipped`).
- `heic`/`heif` : le runtime de référence n'a **pas** `pillow-heif`
  (dépendance lourde non ajoutée) : l'original est référencé intact,
  `status=ready`, `analysis_status=skipped`, message d'erreur explicite
  dans la photo. Si `pillow-heif` est installé, le décodage fonctionne
  normalement.

### Interface « Stockage »

Bouton **Stockage** dans l'en-tête de la page Photos (permission
`photos.view`) : backend, chemin, statut en direct, scan auto,
dernier scan (détail) + boutons **Scanner maintenant**
(`photos.upload`) et **Vérifier le stockage**.

### API

| Endpoint | Rôle |
|---|---|
| `GET /photos/storage/status` | Backend, chemin, `available/unavailable/error`, dernier scan (`photos.view`) |
| `POST /photos/import/scan` | Enfile `scan_import` (202, anti-doublon ; 409 si stockage indisponible) (`photos.upload`) |

### Monitoring périodique

Si `PHOTO_NAS_SCAN_ENABLED=true`, la boucle `_photo_job_loop` enfile un
scan automatique lorsque le dernier est plus ancien que
`PHOTO_NAS_SCAN_INTERVAL_SECONDS` (min. 30 s). Le propriétaire du scan
est celui du dernier scan — aucun scan automatique avant un premier scan
manuel (pas d'attribution hasardeuse d'une photothèque).

## Architecture

```
src/public/js/pages/PhotosPage.js     grille + vues + lightbox + retouche
src/public/js/services/photosApi.js   client REST (/photos)
src/public/css/photos.css             styles (tokens existants)
app/api/photos.py                     router FastAPI (/photos…)
app/services/photo/                   storage (backends local/NAS), metadata,
                                      thumbnails, analysis, quality,
                                      embeddings, edits, jobs, scan (V3),
                                      ai_search, face_detection,
                                      face_grouping, service, tools
app/models/photo.py                   14 tables SQLAlchemy
app/schemas/photos.py                 schémas Pydantic
app/modules/photos.py                 module sidebar/nav (PHOTO_ENABLED)
alembic/versions/20261003_0034_…      migration
```

### Jobs

| Type | Rôle | Chaînage |
|---|---|---|
| `ingest` | EXIF + miniatures + lieu | → `analyze` (si analyse active) sinon → `embedding` ; → `face_detect` si l'analyse n'est pas déjà en file |
| `analyze` | Provider d'analyse + qualité + tags | réussite → `face_detect` + `embedding` ; échec → retry (backoff, 3 essais) |
| `embedding` | Vecteur image (upsert, sauf si à jour) | terminal |
| `face_detect` | Détection des visages (état kind "faces") | visages > 0 → `face_embedding` ; échec → retry (backoff, 3 essais) |
| `face_embedding` | Regroupement des visages non affectés (centroïdes) | terminal |
| `scan_import` | Scan/import idempotent du stockage (V3, photo_id nul) | terminal (état dans `photo_scan_runs`) |

Anti-doublons : `enqueue_job_unique` ne crée pas de second job
`analyze`/`embedding` en attente pour une même photo (le job existant est
réutilisé). Statut visible côté UI : pastille par tuile + ligne
« Analyse IA » de la visionneuse.

- Routes SPA : `/photos`, `/photos/albums`, `/photos/people`, `/photos/places`,
  `/photos/favorites` (permission `photos.view`).
- Le service worker a été bumpé (`forgeai-static-v6`) pour invalider le cache
  statique ; versions `photos.css?v=4`, `PhotosPage.js?v=4`, `photosApi.js?v=3`,
  `app-erp.js?v=62` (V3 : section Stockage).
- Pillow est ajouté à `pyproject.toml` (installation via `pip install -e .`).

## Configuration (`.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `PHOTO_ENABLED` | `true` | Active le module et la nav |
| `PHOTO_STORAGE_PATH` | `data/photos` | Originaux + miniatures + versions |
| `PHOTO_MAX_UPLOAD_SIZE` | `52428800` | Taille max par fichier (octets) |
| `PHOTO_THUMBNAIL_SIZES` | `96,256,640,1280,2048` | Largeurs des miniatures |
| `PHOTO_BACKGROUND_JOBS` | `true` | Boucle lifespan + `BackgroundTasks` |
| `PHOTO_JOB_POLL_SECONDS` | `2` | Intervalle de la boucle de jobs |
| `PHOTO_ANALYSIS_ENABLED` | `true` | Analyse de métadonnées après ingest |
| `PHOTO_ANALYZER` | `metadata` | Analyseur (`metadata` = actif) |
| `PHOTO_QUALITY_ENABLED` | `true` | Score de qualité dans `result_json` |
| `PHOTO_EMBEDDING_ENABLED` | `true` | Embedding image (photos similaires) |
| `PHOTO_EMBEDDING_PROVIDER` | `local_grid` | Provider d'embedding (local) |
| `PHOTO_ANALYSIS_THUMB_SIZE` | `medium` | Miniature utilisée pour analyse/embedding/détection |
| `PHOTO_FACE_ENABLED` | `true` | Détection de visages (jobs `face_detect`) |
| `PHOTO_FACE_DETECTOR` | `local_heuristic` | Détecteur (registre `face_detection`) |
| `PHOTO_FACE_GROUPING_ENABLED` | `true` | Regroupement automatique des visages |
| `PHOTO_FACE_GROUP_THRESHOLD` | `0.90` | Similarité min. pour rejoindre un groupe |
| `PHOTO_FACE_GROUP_MERGE_THRESHOLD` | `0.97` | Similarité min. pour fusionner deux anonymes |
| `PHOTO_AI_SEARCH_ENABLED` | `true` | Enrichissement IA de la recherche |
| `PHOTO_GEOCODING_ENABLED` | `false` | Réserve pour le géocodage inverse |
| `PHOTO_STORAGE_BACKEND` | `local` | Backend des originaux (`local` \| `nas`) |
| `PHOTO_NAS_PATH` | `` | Racine NAS montée (si `nas`) |
| `PHOTO_NAS_SCAN_ENABLED` | `false` | Scan automatique périodique (V3) |
| `PHOTO_NAS_SCAN_INTERVAL_SECONDS` | `300` | Intervalle minimal entre deux scans |

## Permissions

`photos.view`, `photos.upload`, `photos.update`, `photos.delete`,
`photos.albums.manage`, `photos.people.manage`, `photos.edit`, `photos.analyze`,
`photos.manage_all` — ajoutées à `default_permissions` de `app/services/rbac.py`
(le rôle `admin` les reçoit au prochain seed).

## Migration

`alembic/versions/20261003_0034_photos_module.py` (14 tables, `down_revision`
`20260930_0033`) — à appliquer via `alembic upgrade head`. Contient aussi
`photo_analyses.version` (version du provider d'analyse), la colonne
`photos.storage_backend` (V3) et la table `photo_scan_runs` (V3).

## Tests

`tests/test_photos.py` (34 tests) : import/storage, EXIF, orientation, GPS → lieu,
pagination curseur, favoris, suppression logique, isolation inter-utilisateurs,
permissions, albums, personnes/visages, tags, recherche naturelle, jobs,
retouche (rotate cumulatif / revert / 501 IA), doublons, navigation, téléchargement
non latin-1, atomicité upload, job orphelin.

`tests/test_photos_ai.py` (V1) : succès/échec/réessai de l'analyse, ré-analyse,
changement de provider, embedding (création, dédup, changement de modèle),
photos similaires (scores, isolation inter-utilisateurs, photo non indexée),
recherche naturelle combinée, concurrence de jobs.

`tests/test_photos_people.py` (V2, 19 tests) : chaîne de détection (détecteur
local et factices), groupes anonymes / isolation des groupes nommés, fusion
(cible/source, adoption de nom), séparation, couverture, compteurs après
suppression de photo, recherche par nom de personne, recadrage privé et
isolation inter-utilisateurs, réessais du job de détection, ré-indexation
après changement de version du détecteur, fusion d'anonymes proches.

`tests/test_photos_storage.py` (V3, 24 tests) : backends local/NAS,
chemins (traversal, unicité, symlinks), suppression NAS impossible,
upload en mode NAS, suppression logique sans toucher les fichiers, scan
(sous-répertoires, lots multiples, idempotence, dédup hash, déplacement,
vidéos, HEIC sans pillow-heif, interruption + reprise), indisponibilité
(abort sans suppression), isolation des backends, endpoints
(statut/scan/409/permissions), scan périodique (intervalle,
anti-doublon), lecture d'une photo après changement de configuration.

Dans `tests/conftest.py` : `PHOTO_BACKGROUND_JOBS=false`,
`PHOTO_AI_SEARCH_ENABLED=false` et un `PHOTO_STORAGE_PATH` temporaire — les
tests consomment les jobs explicitement (`process_photo_jobs`).

## Reste à faire (hors V1)

- Analyseur vision `llm_vision` (nécessite une entrée image côté AI Gateway).
- Analyseur local `local_vision` (classification/détection par modèle léger).
- Ré-indexation en lot (backfill) des photos importées avant la V1 — en
  attendant, chaque photo se ré-indexe individuellement via
  `POST /photos/{id}/embeddings`.
- Encodeur texte pour interroger les embeddings par mots-clés (actuellement
  la similarité part d'une photo source : `GET /photos/{id}/similar`).
- Géocodage inverse (`PHOTO_GEOCODING_ENABLED`).
