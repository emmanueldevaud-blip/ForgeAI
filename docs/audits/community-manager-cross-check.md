# Cross-check — Audit Community Manager (ForgeAI)

**Date :** 2026-11-27
**Dépôt audité :** `D:\ForgeAI` (worktree `D:\ForgeAI`)
**Périmètre de la mission :** vérification indépendante croisée du rapport `docs/audits/community-manager-audit-complet.md`.
**Nature :** audit lecture seule. Aucun code applicatif, aucun test, aucune base, aucun secret, aucune configuration réelle, aucun contenu Meta, aucune publication, aucun commit n’a été modifié. Ce document est le seul livrable ajouté.

---

## 1. Méthodologie et niveaux de preuve

### 1.1 Niveaux utilisés dans cette cross-check

| Sigle | Niveau | Couverture dans cette mission |
|---|---|---|
| **C** | Code présent | **Oui** — relecture intégrale des zones critiques (frontend Publisher/Calendar/Store/Service, endpoints CM, services Studio/Meta/Jobs). |
| **T** | Test automatisé | **Oui** — re-exécution partielle et ciblée (`pytest`, `node --test`). |
| **I** | Interface réelle | **Non** — non observable dans cet environnement (pas de navigateur/CDP serveur). |
| **M** | API externe réelle | **Non** — aucun appel réseau Graph API, aucun compte réel. |

### 1.2 Commandes et contrôles exécutés

- **Backend** (`.venv/Scripts/python.exe -m pytest …`) :
  - Suite ciblée `tests/community_manager` (avec stub hors dépôt `jwt` pour contourner l’absence de `PyJWT` dans cet environnement) : **140 passed / 12 failed** en 230 s.
  - Suites connexes lancées et **vertes** : `tests/test_meta_config_publish.py`, `tests/test_meta_story_publish.py`, `tests/test_studio_story_flow.py`, `tests/test_calendar_suggestions.py`, `tests/test_ig_music.py`, `tests/test_sport_publications.py` (cumul ~65 tests verts sur ces fichiers).
- **Frontend** (`node --test …`) :
  - Suites ciblées Publisher/Music/Story/Store/Preview/Layout/Creation/Tools/Studio/Composer : **9/9 suites vertes**.
  - `tests/frontend/editor_v1.test.mjs` → **échec reproduit** : `ERR_UNSUPPORTED_ESM_URL_SCHEME` (`Received protocol 'd:'` — chemins absolus Windows `D:\…` non encodés en `file://` sous Node 26.13.1).
  - `tests/frontend/garmin_quick_publication.test.mjs` → **échec reproduit** : fichier `src/public/js/pages/GarminQuickPublicationView.js` absent (ancien parcours non routé).
- **Non exécutés** (inchangé) : Playwright `e2e_music_workflow.mjs` / `e2e_step_restore.mjs` (serveur `localhost:8000` / Chrome CDP absents), validation Meta réelle, rendu navigateur.

### 1.3 Limites explicites

- L’environnement backend a nécessité le stub `jwt` hors dépôt (non fusionné, non commité) : les 12 échecs CM sont donc des échecs **réels** une fois la collecte franchie, pas un artefact de stub.
- Les preuves I/M demeurent non acquises : seuls les niveaux C et T ont été re-mobilisés.

---

## 2. Verdict global de la cross-check

**Verdict global : PARTIELLEMENT CONFIRMÉ / CONFIRMÉ selon les constats.**

- Les constats **P0/P1 majeurs A01–A10 sont confirmés** par re-vérification code + reproduction des échecs backend/frontend.
- Deux diagnostics initiaux comportaient une **nuance** (A02 : double création de brouillon ; A09 : granularité des permissions).
- Aucun constat majeur du rapport n’a été infirmé par la re-vérification.

**Conclusion provisoire :** avant toute correction fonctionnelle, le blocage n°1 (A01) et les chaînes de création (A02, A03) doivent être résolus ; la fiabilité de release (A10) reste insuffisante tant que les suites ne sont pas stabilisées.

---

## 3. Détail des constats — verdict, preuves et écart

### 3.1 A01 — Publication standalone impossible depuis un brouillon local (P0) — **CONFIRMÉ**

- **Verdict :** Confirmé.
- **Preuves (code) :**
  - `src/public/js/services/publisherDraftService.js:100-107` — `createBlank()` : `publisherStore.resetDraft(format); this.currentDraftType = …; this.currentDraftId = null;`
  - `src/public/js/services/publisherDraftService.js:355-356` — `publish()` : `if (!this.currentDraftId) throw new Error('Aucun brouillon');`
  - `src/public/js/pages/CommunityPublisherPage.js:111-123` — branche `freshDraft` → `createBlank` ; `141-162` `_restoreOrResetDraft()` ; `199-203` `_loadFromGarmin()` ; `183-197` `_loadFromCalendarEntry()`.
  - `src/public/js/pages/CommunityPublisherPage.js:799-817` — `_saveDraft()` : sans `currentDraftId`, toast « Brouillon sauvegardé localement » (aucun persistance serveur).
  - `src/public/js/pages/CommunityPublisherPage.js:819-839` — `_publish()` : appelle `publisherDraftService.publish({ platforms: ['instagram'] })` ; exige un brouillon serveur.
- **Reproduction :** flux standalone (`/publisher/post`, bouton « ＋ Créer une publication » via `freshDraft`, ou `/publisher/post?garmin=<id>`) → aucun `currentDraftId` serveur possible → `publish()` lève « Aucun brouillon » → `_showError` (alert `.publisher-alert`).
- **Écart :** diagnostic initial exact ; la racine est la conception « local-only par défaut » sans création serveur de brouillon.
- **Verdict final :** **CONFIRMÉ — P0 bloquant.**

### 3.2 A02 — `publication_id` transmis comme `calendar_entry_id` (P1) — **CONFIRMÉ** (diagnostic initial **partiellement** complet)

- **Verdict :** Confirmé ; diagnostic initial juste sur la confusion, mais **incomplet sur le mécanisme** (il sous-estimait la double création).
- **Preuves (code) :**
  - `src/public/js/pages/CommunityManagerCalendarPage.js:352-360` — `_openEntry()` : `createStudioDraftFromCalendar({ calendar_entry_id: entryId, … })` → `res.publication_id` → `_openPublisher({ entryId: res.publication_id, format: 'post' })`.
  - `src/public/js/pages/CommunityPublisherPage.js:183-197` — `_loadFromCalendarEntry()` : `publisherDraftService.createFromCalendar({ calendarEntryId: this.entryId, … })`.
  - `src/public/js/services/publisherDraftService.js:57-74` — `createFromCalendar()` : POST `/community-manager/studio/from-calendar` avec `{ calendar_entry_id: calendarEntryId }`.
  - `app/api/community_manager.py:293-312` (endpoint) et `app/services/community_manager/studio.py:610-655` (service) : recherche `EditorialCalendarEntry.id == data.calendar_entry_id`.
  - `app/schemas/sport.py:331-339` — `PublicationGenerateFromCalendarRequest.calendar_entry_id: int`.
- **Reproduction :** l’entrée du calendrier déclenche **deux** appels de création (une via `_openEntry`, une via `_loadFromCalendarEntry` via le rechargement) et le second envoie un `publication_id` là où un `calendar_entry_id` est attendu → incohérence fonctionnelle avérée.

### 3.3 A03 — Photos suggérées Garmin appelées avec `null` (P1) — **CONFIRMÉ**

- **Verdict :** Confirmé.
- **Preuves :**
  - `src/public/js/services/sportApi.js:298-300` — `getSuggestedPhotos(publicationId, limit)` : interpolation directe dans l’URL (`/community-manager/studio/draft/${publicationId}/suggested-photos`).
  - `app/api/community_manager.py:571-581` — route `publication_id: int` (Query `ge=1, le=50`).
  - `src/public/js/pages/CommunityManagerCalendarPage.js:336` — `getSuggestedPhotos(null, 20)`.
  - `src/public/js/components/PublisherMediaPicker.js:494-502` — `_openGarminActivity()` : `getSuggestedPhotos(null, 50)` **et ignore le résultat**.
- **Reproduction :** tout parcours Garmin (calendrier + MediaPicker) construit une URL `…/draft/null/suggested-photos` → rejet côté API.

### 3.4 A04 — Programmation stockée mais jamais exécutée / absente UI (P1) — **CONFIRMÉ**

- **Verdict :** Confirmé.
- **Preuves :**
  - `app/services/community_manager/studio.py:1297-1312` — `schedule_publication()` écrit `status="scheduled"` / `scheduled_at`.
  - `app/services/community_manager/studio.py:1920-1921`, `:2102-2103`, `:2270-2271` — les trois points de publication (IG / FB / both) refusent tout statut hors `("validated", "draft")`.
  - `app/main.py:66-67, 217-247` — boucle jobs uniquement si `PHOTO_ENABLED`; aucun consommateur de `status=scheduled`.
  - `src/public/js/services/sportApi.js:246-248` — `scheduleStudioDraft` exporté, **aucun appel interne**.
- **Preuve complémentaire :** `tests/community_manager/test_v3_publish.py:1268-1282` — `test_publish_to_instagram_not_validated` : publication `status="scheduled"` → `ValueError « Seules les publications validées »`.

### 3.5 A05 — Carrousel sélectionnable mais publié en photo unique (P1) — **CONFIRMÉ**

- **Verdict :** Confirmé.
- **Preuves :**
  - `app/services/community_manager/studio.py:702-808` (notamment `:724-739`) — `update_draft` : `design["carousel"] = ids; pub.photo_id = ids[0]`.
  - `app/services/community_manager/studio.py:1870-1881` — `_publish_media_photo_id()` : une seule source média.
  - `app/services/community_manager/studio.py:1967-1974, 1991-2000` — publication unique (`publish_photo` / `publish_video`), **aucun paramètre album/`children`**.
  - `app/services/sport_instagram_publish.py:196-258` — `create_media_container()` : pas de support album CAROUSEL ; `audio_configuration` réservé Reel.
- **Nuance :** pour les publications sportives Garmin, `_publish_media_photo_id` force `visual_type="reel"` (studio.py:1876-1881) — le carrousel sportif converge vers un Reel mono-média.

### 3.6 A06 — Stories Facebook / `both` annoncées puis refusées (P1) — **CONFIRMÉ**

- **Verdict :** Confirmé.
- **Preuves :**
  - `app/api/community_manager.py:110-112` — `StoryDraftPublishRequest.platforms: List[str] = ["instagram"]  # instagram, facebook, both, List, Dict, Any`.
  - `app/api/community_manager.py:1096-1097` — refus `any(platform != "instagram")`.
  - `app/api/community_manager.py:1118` — le payload job conserve `platforms` (mais handler en dur Instagram).
  - `app/services/photo/jobs.py:654-659` — handler `publish_story` sans support multi-plateforme.

### 3.7 A07 — Musique Story sélectionnée/sauvegardée mais non publiée (P1) — **CONFIRMÉ**

- **Verdict :** Confirmé (pour la Story).
- **Preuves :**
  - Frontend : `publisherDraftService.js:240-242` (save → `audio_configuration` pour Story), `storyPublishPipeline.js:117-119` (payload save), `PublisherMusicStep.js` (sélection UI).
  - Backend : `app/api/community_manager.py:97, 888-889` (persistance `audio_configuration`), orchestrateur.
  - Job Story : `app/api/community_manager.py:1118` (payload job sans `audio_configuration`) → `app/services/photo/jobs.py:654-659` → `sport_instagram_publish.publish_story()` (460-478) **sans paramètre audio** ; `create_media_container` n’applique l’audio qu’au Reel (`is_reel`, sport_instagram_publish.py:244-251).
- **Nuance positive vérifiée :** le chemin **Reel** transmet bien `audio_configuration` (`design.ig_audio` → `publish_video(audio_configuration=…)`), confirmé par les tests Meta (`tests/test_meta_config_publish.py::test_publish_reel_attaches_audio_configuration` vert).

### 3.8 A08 — Quick publish Garmin incomplet (P1) — **CONFIRMÉ**

- **Verdict :** Confirmé.
- **Preuves :** `src/public/js/pages/SportActivitiesPage.js:23-25` → `/publisher/post?garmin=<id>` ; `src/public/js/app-erp.js:461-466` ; `src/public/js/pages/CommunityPublisherPage.js:199-203` (`_loadFromGarmin` → `setGarmin` seul) ; `src/public/js/components/PublisherMediaPicker.js:494-502` (suggestions `null` + ignore).

### 3.9 A09 — Permissions de route et d’action incohérentes (P1) — **CONFIRMÉ** (nuance)

- **Verdict :** Confirmé sur le fond ; granularité à affiner.
- **Preuves :** `app/api/community_manager.py:123-176` (lecture via `strategy_view`/`calendar_view`, écriture via `strategy_update`/`calendar_generate`), `app/api/community_manager.py:293-312` (écriture Studio via `calendar_generate`).
- **Nuance :** le module (`app/modules/community_manager.py:18-30`) grade l’accès via `community_manager.strategy_view` ; les endpoints d’écriture avancés exigent `community_manager.calendar_generate` — d’où un utilisateur en lecture seule qui ouvre un flux d’écriture → 403.

### 3.10 A10 — Suites de tests rouges / confiance release insuffisante (P1) — **CONFIRMÉ** (reproduction faite)

- **Verdict :** Confirmé et **reproduits**.
- **Preuves backend :** `tests/community_manager` → **12 failed / 140 passed** : `test_studio_caption_sync.py::test_feed_preview_sets_explicit_dark_text_color` (CSS var vs `#111827`) ; `test_v3_publish.py::test_validate_empty_content_fails` ; `TestPublishAPI::test_publish_draft_success` / `test_publish_draft_validation_error` (missing `background_tasks`) ; `TestInstagramCaptionLength` (8 échecs : `_sport_stats_from_activity` avec `AsyncMock`).
- **Preuves frontend :** échec reproduit (`ERR_UNSUPPORTED_ESM_URL_SCHEME`) ; échec reproduit (fichier Garmin supprimé).
- **Verdict final :** **CONFIRMÉ — bloque toute mise à disposition.**

### 3.11 Constats complémentaires A11–A24 — verdicts

| Constat | Verdict |
|---|---|
| A11 Sélecteur compte Instagram sans persistance | **CONFIRMÉ** (`publisherDraftService.save()` ne transmet pas `accountId`; `_syncStoreFromStudio` réinitialise `accountId: null`). |
| A12 Bouton « Accepter » déclenche création de brouillon + ouverture Publisher | **CONFIRMÉ** (`CommunityManagerCalendarPage.js:598-602` → `_openEntry`). |
| A13 Boutons inopérants / absents (report, régénération) | **CONFIRMÉ** (`_rescheduleSuggestion` jamais câblée ; handler `regenerate-hashtags` sans bouton rendu). |
| A14 Normalisation fragile des IDs médias | **CONFIRMÉ** (`publisherDraftService.js:236-238` ; ids `media_<ts>` perdus silencieusement). |
| A15 `publish_to_both` succès partiel marqué `shared` | **CONFIRMÉ** (`studio.py:2394-2417`). |
| A16 Jobs CM dépendants du module Photos | **CONFIRMÉ** (`app/main.py:66-67`). |
| A17 `job_id` manquant dans le payload de rendu Story | **CONFIRMÉ** (bookkeeping `render_jobs`/progress). |
| A18 Doublon `FORMAT_CONFIG` | **CONFIRMÉ** (`publisherStore.js:16-49` vs `CommunityPublisherPage.js:45-78`). |
| A19 Pages héritées non routées / test obsolète | **CONFIRMÉ** (`app-erp.js:26-33` imports vs routes ; `garmin_quick_publication.test.mjs`). |
| A20 Régénération sans filtre d’appartenance | **CONFIRMÉ** (`app/api/community_manager.py:1621-1629` → `SportGarminConnectService.regenerate_publication_content` sans scoping utilisateur ; par contraste `SportPublicationService.get_publication` filtre par athlète). |
| A21 `TypeError` non bloquant sur le bouton Suivant | **CONFIRMÉ** (`CommunityPublisherPage.js:640-660` appelle `.catch()` sur le résultat de `_navLock` qui retourne `undefined`; `_navLock` :672-685). |
| A22 Détection d’extension vidéo inefficace | **CONFIRMÉ** (`sport_instagram_publish.py:157-170`). |
| A23 Page Facebook stockée dans le champ Instagram | **CONFIRMÉ** (`sport_instagram_publish.py:71-90, 661-701`). |
| A24 Libellés/scripts E2E non exécutés en conditions réelles | **CONFIRMÉ** (inchangé). |

---

## 4. Focus — dépendances entre A01, A02, A03 et A14

1. **A01 ↔ A02 :** le flux « création depuis calendrier » (A02) passe d’abord par `_openEntry` (création brouillon) puis par `_loadFromCalendarEntry` (re-création + mauvais ID). Le flux standalone (A01) n’a aucun brouillon serveur. Les deux partagent le même `CommunityPublisherPage` ; la correction A02 (charger le brouillon par `publication_id`) est le levier naturel du lot de création.
2. **A03 ↔ A02/A01 :** les entrées Garmin (`source === 'garmin'`) du calendrier sont traitées dans `_openEntry` via `getSuggestedPhotos(null, 20)` (A03) puis `createStoryDraft` — le parcours de création Garmin est donc conditionné par A03, en amont de la publication (A01).
3. **A14 ↔ A01 :** un brouillon standalone (A01) vit dans le store local ; la sauvegarde locale (`_saveDraft`) ne persiste que le store et la normalisation `photo_ids` (A14) peut vider une sélection (`media_<ts>` → `NaN` filtré) — interaction à lever dans le lot création.

---

## 5. Risques et dépendances

- **Risque principal :** une création standalone aboutit à un état non publiable (A01) ; une création calendrier aboutit à un ID erroné (A02) → le module reste non livrable malgré un socle backend « vert ».
- **Dépendances identifiées :** jobs `community_publish` ↔ boucle `PHOTO_ENABLED` (A16) ; musique Reel ↔ Audio API Meta (A07) ; album CAROUSEL ↔ contrat Meta (A05) ; scheduler ↔ absence consommateur (A04).
- **Risque de non-régression :** la correction A01/A02/A03 touche le chaînage frontend↔backend ; la correction A05/A07 touche le contrat Meta côté service.

---

## 6. Proposition de périmètre définitif pour le Lot 0 (création publiable)

Sur la base de la cross-check, le **Lot 0 définitif** devrait couvrir :

1. **A01** : création serveur de brouillon standalone (endpoint dédié ou création à la volée au premier `save`/`publish`), avec conservation du brouillon local en attendant.
2. **A02** : ouvrir le Publisher via `publication_id` (chargement) sans re-création ni réinterprétation en `calendar_entry_id`.
3. **A03** : suggestions Garmin par `activity_id` (ou création de brouillon puis utilisation de l’ID).
4. **A14** : normalisation robuste des IDs médias (conservation d’un `photoId` numérique explicite, erreur visible sinon).

Critères de sortie du Lot 0 : création standalone → save → publish OK ; calendrier → création → Publisher OK ; Garmin → suggestions → StoryDraft OK ; carrousel → album Meta (A05) hors périmètre strict si décision produit « bloquer ».

---

## 7. Critères d’acceptation vérifiables (Lot 0 / post-cross-check)

1. `pytest tests/community_manager …` → **0 échec** sur les suites Community Manager (triage des 12 échecs A10 en cours).
2. `node --test` sur les suites Publisher/Music/Story/Studio/Garmin → **0 échec** (dont correction du harness ESM Windows et archivage du test obsolète A19).
3. Scénario E2E navigateur : création standalone → sauvegarde → publication ; création calendrier → publication ; Garmin → Story.
4. Tests unitaires : `createBlank → save → publish` ; chaîne calendrier → Publisher ; suggestions Garmin ; normalisation IDs (A14).

---

## 8. Ce qui reste à valider (hors cross-check)

- **Propriétaire du module :** arbitrage produit A05 (album vs blocage), A06 (Story FB), A07 (musique Story), A04 (scheduler), A09 (matrice RBAC).
- **Coordinateur :** arbitrage final du cross-check avant tout lot.
- **Humain / interface / Meta :** validation navigateur réel + validation Meta réelle (comptes de test) — non couvertes par cette mission.

---

**Fin du document de cross-check.**
