# Audit complet — Module Community Manager (ForgeAI)

**Date :** 2026-11-27  
**Dépôt audité :** `D:\ForgeAI`  
**Périmètre :** dashboard/calendrier éditorial, Publisher, Studio, Stories, musique, Instagram/Facebook, programmation, comptes/config Meta, Garmin, suggestions, erreurs/états vides, responsive, liens morts/boutons inopérants.  
**Nature :** audit lecture seule. **Aucun code applicatif, test, migration, base, secret, configuration réelle ni contenu Meta n’a été modifié ou publié.** Le présent rapport est le seul livrable ajouté par cet audit. Un fichier non suivi externe à ce travail peut être présent dans le dépôt ; il n’a pas été touché.

> **Décision de gouvernance :** ce rapport doit être validé par le propriétaire du module avant toute correction. Le coordinateur doit effectuer une vérification croisée des anomalies P0/P1 avant la conclusion définitive. Aucun lot de correction n’a été démarré.

---

## 1. Méthode et niveaux de preuve

### 1.1 Niveaux de validation utilisés

| Sigle | Niveau | Signification |
|---|---|---|
| **C** | Code présent | Le comportement est déduit de la lecture du code. Aucune exécution fonctionnelle. |
| **T** | Test automatisé | Le scénario est couvert par un test exécuté ou par un test statique du dépôt. |
| **I** | Interface réelle | Le parcours a été observé dans un navigateur avec l’application réelle. |
| **M** | API externe réelle | Le résultat a été validé avec Meta/Graph API sur un compte réel. |

**Résultat global :** `C = oui`, `T = partiel (183 backend / 11 frontend passent ; 12 backend / 10 frontend échouent)`, `I = non`, `M = non`.  
Tout ce qui est marqué « opérationnel » ci-dessous l’est **uniquement au niveau C ou T**. Rien n’a été déclaré validé en interface ni avec Meta.

### 1.2 Commandes et contrôles exécutés

- Lecture des routes/services/composants listés dans les sections 3 à 7.
- Backend :
  - `.venv\Scripts\python.exe -m pytest tests/community_manager tests/test_ig_music.py tests/test_meta_config_publish.py tests/test_meta_story_publish.py tests/test_studio_story_flow.py tests/test_calendar_suggestions.py -q --disable-warnings`
  - Le premier lancement a échoué sur `tests/test_studio_caption_sync.py` (fichier inexistant à cette racine ; le fichier réel est `tests/community_manager/test_studio_caption_sync.py`).
  - Le second a échoué à la collecte sur `import jwt` dans `tests/community_manager/test_v3_publish.py:11`, alors que `PyJWT>=2.8.0` est déclaré dans `pyproject.toml:18` mais absent des deux interpréteurs disponibles.
  - Troisième exécution : import `jwt` neutralisé par un **stub hors dépôt** (`%TEMP%\forgeai_audit_pystub\jwt.py`) car l’import est inutilisé dans le fichier de test. Résultat : **183 passés, 12 échecs, 7 warnings, 337,68 s**. Le stub n’a pas été ajouté au dépôt.
- Frontend :
  - `node --test tests/frontend/*.test.mjs tests/frontend/*.test.js` → **11 tests passent, 10 échecs**.
  - Échecs : 9 tests `editor_*` pour `ERR_UNSUPPORTED_ESM_URL_SCHEME` (chemins Windows `D:\...` passés au chargeur ESM Node sous Node 26.13.1) et 1 test Garmin pour fichier absent `src/public/js/pages/GarminQuickPublicationView.js`.
- Scripts Playwright `e2e_music_workflow.mjs` et `e2e_step_restore.mjs` : **non exécutés**. Ils exigent un serveur sur `localhost:8000` et un Chrome/CDP sur `127.0.0.1:9222` ; aucun de ces ports n’écoutait au moment de l’audit. De plus, ils mockent les appels (`auth/me`, `photos`, musique), donc ils ne valideraient pas Meta.
- Aucun appel réseau réel vers Graph API, aucun test de publication réelle, aucune lecture/affichage de secret.

### 1.3 Limites explicites

- **Meta non validé** : création de container, acceptation de `media_type=REELS/STORIES`, transmission de `audio_configuration`, résolution du token de Page, scopes/tâches `/me/accounts`, accessibilité externe des URL signées : tout est vérifié uniquement côté code/tests mockés.
- **Interface non validée** : rendu réel desktop/mobile, toasts, modales, scroll, états vides, navigation clavier/tactile non observés.
- **Planification non validée** : aucun ordonnanceur externe hors dépôt n’a pu être inspecté ; en l’état du code, aucun consommateur de `status=scheduled` n’existe.
- **Permissions réelles** : seules les déclarations de routes et de dépendances ont été lues ; aucun jeu de droits utilisateur réel n’a été testé.

---

## 2. Synthèse exécutive

Le module dispose d’une base backend substantielle (50 routes Community Manager, services Studio/Story, file de jobs, intégration Meta centralisée) et de tests automatisés nombreux. Toutefois, **le parcours unifié Publisher n’est pas encore dans un état livrable** : la création standalone aboutit à un brouillon purement local que la publication refuse ; la création depuis le calendrier mélange deux identifiants ; la programmation et Facebook existent côté service/API mais ne sont pas exposées dans le wizard ; les Stories et la musique ont des contrats contradictoires ; plusieurs suites de tests sont rouges.

**Anomalies bloquantes avant toute mise à disposition utilisateur :**

1. **P0 — Publication standalone impossible** (`createBlank` → `currentDraftId = null` → `publish()` lève « Aucun brouillon »).
2. **P1 — `publication_id` transmis comme `calendar_entry_id`** depuis le calendrier vers Publisher.
3. **P1 — Suggestions photos Garmin appelées avec `null`** sur une route à paramètre entier obligatoire.
4. **P1 — Programmation stockée mais jamais exécutée**, et absente de l’UI.
5. **P1 — Carrousel sélectionnable mais publié comme photo unique** (aucun `children`/album Meta).
6. **P1 — Stories Facebook/`both` refusées malgré un schéma qui les annonce**.
7. **P1 — Musique Story sauvegardée mais non transmise à Meta**, avec libellé UI « non intégrable ».
8. **P1 — Quick publish Garmin incomplet** (aucune sélection de photos ni statistiques chargées automatiquement).
9. **P1 — 12 tests backend et 10 tests frontend échouent** ; la confiance de release est insuffisante.

**Points positifs vérifiés au niveau code/test :**

- Routes CM complètes et permissions déclarées de manière explicite (`app/api/community_manager.py:116-176`).
- Configuration Meta centralisée, secrets chiffrés, test de diagnostic sans publication (`app/api/admin.py:199-258`, `:261-530`).
- Unified Login Meta avec `state` CSRF et callback public contrôlé (`app/api/sport_publications.py:220-473`).
- Séparation Reel/Story de la musique : Reel envoie bien `audio_configuration`, Story ne le fait pas (cohérence interne, mais voir anomalie A07).
- Restauration d’étape du Publisher couverte par tests (`tests/frontend/community_publisher_page.test.mjs`, `e2e_step_restore.mjs`).
- Pipeline Story documenté : export JPEG → upload → `published_photo_id` → validation → publication (`tests/frontend/story_publish_pipeline.test.mjs`).

---

## 3. Matrice de couverture

Légende : **C** code lu, **T** test automatisé, **I** interface réelle, **M** Meta réel. « — » = aucun élément trouvé.

| # | Parcours / fonction | C | T | I | M | Verdict | Preuves principales |
|---|---|---:|---:|---:|---:|---|---|
| 1 | Dashboard / route `/community-manager` | ✅ | — | ❌ | n/a | Route réelle vers le calendrier uniquement ; pas de route `/community-manager/dashboard`. | `app-erp.js:359-361,438-451` ; `app/modules/community_manager.py:32-50` |
| 2 | Calendrier mois/semaine | ✅ | ✅ partiel | ❌ | n/a | Chargement + rendu codés ; aucun test dédié à `CommunityManagerCalendarPage`. | `CommunityManagerCalendarPage.js:57,101-132` ; `community_manager.py:1341-1550` |
| 3 | Génération suggestions | ✅ | ✅ | ❌ | n/a | Backend + bouton présents ; permission `calendar_generate`. | `community_manager.py:1553-1558` ; `CommunityManagerCalendarPage.js:160-170` ; `test_calendar_suggestions.py:167-397` |
| 4 | Accepter suggestion | ✅ | ✅ backend | ❌ | n/a | Bouton UI « Accepter » détourné vers ouverture complète du Publisher (A12). | `CommunityManagerCalendarPage.js:320-323,596-601` |
| 5 | Refuser suggestion | ✅ | ✅ backend | ❌ | n/a | Bouton câblé. | `CommunityManagerCalendarPage.js:172-182,603-609` |
| 6 | Reporter suggestion | ✅ | ✅ backend | ❌ | n/a | Méthode frontend présente **mais aucun bouton/événement** (A13). | `CommunityManagerCalendarPage.js:184-193,565-627` |
| 7 | Régénérer hashtags | ✅ | ✅ backend | ❌ | n/a | Handler enregistré **mais aucun bouton rendu** (A13). | `CommunityManagerCalendarPage.js:208-217,620-626` |
| 8 | Création publication depuis calendrier | ✅ | ✅ backend | ❌ | n/a | Mauvais ID transmis à Publisher (A02). | `CommunityManagerCalendarPage.js:352-360` ; `publisherDraftService.js:57-70` |
| 9 | Création publication standalone | ✅ | ❌ | ❌ | n/a | **Bloquant P0** (A01). | `app-erp.js:365-373` ; `CommunityPublisherPage.js:111-123,799-839` ; `publisherDraftService.js:100-107,355-356` |
| 10 | Publisher post / réouverture brouillon | ✅ | ✅ | ❌ | n/a | Steps, picker, aperçus, restauration d’étape couverts ; publication non couverte. | `publisherStore.test.js`, `community_publisher_page.test.mjs`, `publisher_preview.test.mjs` |
| 11 | Publisher carrousel | ✅ | ✅ partiel | ❌ | n/a | Sélection 2–10 photos ; publication en album absente (A05). | `publisherStore.js:25-32` ; `studio.py:724-739,1870-1881` |
| 12 | Publisher Reel + musique IG | ✅ | ✅ | ❌ | ❌ | `ig_audio` → `audio_configuration` présent pour Reel ; non validé avec Meta. | `studio.py:1752-1768,1991-2000` ; `test_meta_config_publish.py:169-280` |
| 13 | Publisher Story + étape Musique | ✅ | ✅ | ❌ | ❌ | Sélection/persistance OK ; non transmis à Meta (A07). | `PublisherMusicStep.js:87,171-212` ; `jobs.py:654-659` |
| 14 | Story Studio : rendu, validation, publication | ✅ | ✅ partiel | ❌ | ❌ | Pipeline frontend testé ; handler backend `story_slide_publish` non testé ; `job_id` non transmis au handler (A17). | `community_manager.py:924-1135` ; `jobs.py:625-682` ; `story_publish_pipeline.test.mjs` |
| 15 | Publication Instagram | ✅ | ✅ mock | ❌ | ❌ | File `community_publish` + job ; appel Meta mocké uniquement. | `community_manager.py:693-739` ; `test_v3_publish.py` |
| 16 | Publication Facebook Page | ✅ | ✅ mock | ❌ | ❌ | Existe côté API/service ; **aucun bouton dans Publisher**. | `community_manager.py:755-780` ; `studio.py:2065-2234` ; `test_facebook_page_token.py` |
| 17 | Publication Instagram + Facebook (`both`) | ✅ | ⚠️ inspection source | ❌ | ❌ | Service présent ; statut « partiel » marqué `shared` (A15). | `community_manager.py:783-808` ; `studio.py:2394-2417` |
| 18 | Programmation | ✅ | ❌ | ❌ | ❌ | API + client exports, aucun UI et aucun worker (A04). | `community_manager.py:541-554` ; `sportApi.js:245-248` ; `studio.py:1297-1312` ; `main.py:60-68` |
| 19 | Reprise après échec / job status | ✅ | ❌ | ❌ | ❌ | `GET /studio/publish-job/{job_id}` existe ; aucun test ni UI de reprise. | `community_manager.py:742-752` ; `jobs.py:789-819` |
| 20 | Comptes / config Meta / OAuth | ✅ | ✅ | ❌ | ❌ | Champs + chiffrement + preflight + callback codés ; non validés avec Meta. | `admin.py:199-258` ; `sport_publications.py:220-473` ; `test_admin_meta_settings.py`, `test_meta_oauth_flow.py` |
| 21 | Garmin → Story depuis calendrier | ✅ | ✅ service | ❌ | ❌ | Création StoryDraft correcte ; dépend de `getSuggestedPhotos(null)` (A03). | `CommunityManagerCalendarPage.js:331-350` ; `story_orchestrator.py:76-119` |
| 22 | Garmin → Quick publish depuis activités | ✅ | ❌ | ❌ | n/a | Parcours dégradé (A08). | `SportActivitiesPage.js:20-25` ; `app-erp.js:461` ; `CommunityPublisherPage.js:199-203` |
| 23 | Erreurs / états vides | ✅ | ✅ partiel | ❌ | n/a | Alertes Publisher/Calendar présentes ; cas standalone « Aucun brouillon » non couvert. | `CommunityPublisherPage.js:850-855,897-904` ; `CommunityManagerCalendarPage.js:279-285,415` |
| 24 | Responsive desktop/mobile | ✅ CSS | ✅ statique | ❌ | n/a | Media queries présentes ; non observé en navigateur. | `app.css:10032-10120`, `publisher.css:2186-2315`, `story-editor.css:747-890` |
| 25 | Liens morts / boutons inopérants | ✅ | ❌ | ❌ | n/a | 3 anomalies identifiées (A12, A13, A21) + pages héritées non routées (A19). | `CommunityManagerCalendarPage.js:184-217,565-627` ; `app-erp.js:26-33` |

---

## 4. Preuves détaillées

### 4.1 Routage, dashboard et calendrier

- Routes enregistrées : `/community-manager`, `/community-manager/analytics`, `/publisher`, `/publisher/:format`, `/publisher/:format/:entryId` (`src/public/js/app-erp.js:359-373`). Permissions : `community_manager.strategy_view` sauf analytics (`meta_analytics.view`).
- `/community-manager` instancie **uniquement** `createCommunityManagerCalendarPage` (`app-erp.js:438-451`). Il n’existe pas de route `/community-manager/dashboard` dans le dépôt.
- Menu module CM : seulement « Calendrier éditorial » et « Analytics & Intelligence » (`app/modules/community_manager.py:32-50`) ; aucun lien menu vers `/publisher`. Le seul lien frontal vers Publisher est le bouton activité sportive (`SportActivitiesPage.js:20-25`).
- `CommunityManagerPage.js` et `CommunityManagerStudioPage.js` existent mais ne sont pas importés par `app-erp.js` (`app-erp.js:26-33`) ; ils ne sont pas atteignables dans le routage actuel.
- Calendrier : vue `week` par défaut sur mobile (`matchMedia('(max-width: 767px)')`), sinon `month` (`CommunityManagerCalendarPage.js:57`) ; chargements `getMonthCalendar`/`getWeekCalendar` (`:101-132`) ; suggestions generate/refuse/reschedule (`:160-193`) ; régénération hashtags (`:208-217`).
- Ouverture d’une entrée (`:288-367`) :
  - Story existante → `StoryStudioPage` (`:299-302`) ;
  - publication existante → Publisher avec `isExistingPublication: true` (`:304-308`, `:235-255`) ;
  - suggestion `pending` → `acceptSuggestion` (`:320-323`) puis éventuellement passage forcé à `planifié` (`:324-327`) ;
  - Garmin → `getSuggestedPhotos(null, 20)` + `createStoryDraft` (`:331-350`) ;
  - autres → `createStudioDraftFromCalendar` puis Publisher (`:352-360`).

### 4.2 Studio, publication et plateformes

- `community_manager.py` enregistre 50 routes. Points clés :
  - `/studio/from-calendar` (`:293-312`), `/studio/draft/{id}` GET/PATCH (`:315-340`), validate (`:521-538`), schedule (`:541-554`), preview (`:557-568`).
  - `/studio/draft/{id}/publish` → file `community_publish` + `BackgroundTasks` (`:693-739`, `:717-723`) ; `GET /studio/publish-job/{job_id}` (`:742-752`).
  - `/studio/draft/{id}/publish-facebook` (`:755-780`) et `/publish-both` (`:783-808`) sont **synchrones**.
  - `/story-studio/...` : création, list, lecture, PATCH, render-slide, render-jobs, cancel, validate, publish, delete, preview (`:816-1181`).
- `studio.py` :
  - `update_draft()` stocke `photo_ids` dans `design["carousel"]` et met `photo_id = ids[0]` (`:724-739`) ; maximum 10 photos validées (`:894-910`).
  - `validate_for_publication()` ne bloque pas l’absence de visuel (warning seulement, `:1287-1289`).
  - `schedule_publication()` exige `validated` puis écrit `status="scheduled"` et `scheduled_at` (`:1297-1312`).
  - `_publish_media_photo_id()` force `visual_type="reel"` pour toute publication sportive (`:1876-1881`).
  - `publish_to_instagram()` prépare **un seul média** (`:1967-1974`) puis `publish_video` avec `audio_configuration` pour Reel (`:1991-2000`) ou `publish_photo` (`:2002-2006`). Aucun paramètre `children`.
  - `publish_to_both()` résout deux contextes et deux URL signées (`:2294-2334`) ; publie IG puis FB avec erreurs isolées (`:2351-2392`) ; statut `shared` même en succès partiel (`:2394-2417`).
- `sport_instagram_publish.py` : `create_media_container()` photo (`:256-258`), vidéo (`:252-255`), Reel + `audio_configuration` JSON (`:244-251`), Story sans caption (`:236-243`) ; `publish_story()` n’accepte aucun paramètre audio (`:460-478`). Facebook résout un token de Page via `/me/accounts` avec tâches `MANAGE`/`CREATE_CONTENT` (`:503-550`).

### 4.3 Publisher

- `FORMAT_CONFIG` est dupliqué et identique : source `publisherStore.js:16-49`, copie `CommunityPublisherPage.js:45-78`. Les commentaires expliquent la copie par les tests qui suppriment les imports (`publisherStore.js:12-14`, `CommunityPublisherPage.js:41-43`). `post` et `carousel` ont les mêmes 5 étapes.
- Initialisation (`CommunityPublisherPage.js:111-123`) : publication existante, `entryId`, Garmin, `freshDraft`, puis restauration locale. `_restoreOrResetDraft()` (`:141-162`) garde un brouillon local existant.
- `entryId` est toujours interprété comme `calendarEntryId` par la page (`:183-192`) et le service (`publisherDraftService.js:57-63`).
- `createBlank()` ne crée **aucun** brouillon serveur (`publisherDraftService.js:100-107`). `_saveDraft()` affiche « Brouillon sauvegardé localement » sans `currentDraftId` (`CommunityPublisherPage.js:799-817`). `_publish()` appelle `publisherDraftService.publish()` avec `platforms: ['instagram']` (`:819-839`) ; `publish()` exige `currentDraftId` (`publisherDraftService.js:355-356`).
- `publisherDraftService.save()` construit `photo_ids` avec `parseInt(m.id.replace('photo_', ''))` puis filtre `NaN` (`:236-238`). Les IDs non numériques/prefixés différemment (ex. `media_<ts>` créés à `CommunityPublisherPage.js:127-131`) sont silencieusement perdus.
- Aucun sélecteur de plateforme ni de date dans `CommunityPublisherPage.js` / `PublisherPreview.js` ; seul `platforms: ['instagram']` apparaît (`:838`). `scheduleStudioDraft` est exporté (`sportApi.js:245-248`) mais n’est appelé nulle part.
- L’aperçu Story affiche explicitement : « Sélectionnée · non intégrable à la publication actuelle » (`PublisherPreview.js:195-199`) ; l’étape Musique affiche la même limite (`PublisherMusicStep.js:212`).
- `_navLock()` ne retourne rien (`CommunityPublisherPage.js:672-685`) alors que le bouton Suivant appelle `.catch()` dessus (`:658-660`) : `TypeError: Cannot read properties of undefined (reading 'catch')`, déjà ignoré comme préexistant dans `e2e_step_restore.mjs:148-151`.

### 4.4 Stories, musique et Jobs

- `StoryDraftPublishRequest.platforms` est commenté `instagram, facebook, both` (`community_manager.py:110-112`) mais `publish_story_draft` refuse tout autre que `instagram` (`:1096-1097`) ; le payload mis en file conserve `platforms` (`:1118`) alors que le handler enregistre `"platform": "instagram"` en dur (`jobs.py:667-679`).
- `story_orchestrator.py` : format 1080×1920/`platform: instagram` (`:47`), pipeline `_prepare_draft()` (`:140-188`), `_prepare_audio_config()` (`:504-543`) ; `audio_configuration` est bien sauvegardé (`community_manager.py:888-889`, `publisherDraftService.js:370`) mais `meta_service.publish_story()` ne le transmet pas (`jobs.py:654-659`).
- `CommunityPublisherPage._publish()` Story passe par `publishStoryWithPipeline` (`publisherDraftService.js:355-379`) : export/upload → `updateStoryDraft` → validate → publish ; ordre confirmé par `tests/frontend/story_publish_pipeline.test.mjs`.
- Écart rendu : l’API enfile `studio_render`/`story_slide` avec `slide_index` et `photo_id` (`community_manager.py:957-968`) mais le handler `jobs.py:537,583-597` lit un `job_id` dans le payload pour retrouver la slide ; le `job_id` n’est pas inclus dans le payload fourni.
- File de jobs : reprise des `running` orphelins (`jobs.py:45-64,721-745`), retry `30 * attempts` (`:789-819`), boucle lifespan conditionnée à `PHOTO_ENABLED` (`main.py:66-67,217-247`). Les jobs `community_publish` dépendent donc du module Photos.

### 4.5 Garmin

- Deux parcours :
  1. Calendrier CM : entrée `source === 'garmin'` → `getSuggestedPhotos(null, 20)` + `createStoryDraft({activity_id, photo_ids, calendar_entry_id})` (`CommunityManagerCalendarPage.js:331-350`).
  2. Activités sportives : bouton 📸 → `/publisher/post?garmin=<id>` (`SportActivitiesPage.js:20-25`), parsé par `app-erp.js:461`, puis simple `publisherStore.setGarmin()` (`CommunityPublisherPage.js:199-203,875-879`).
- Le MediaPicker liste les activités (`PublisherMediaPicker.js:470-492`), appelle `getSuggestedPhotos(null, 50)` **et ignore le résultat** (`:494-510`).
- `SportGarminPage.js` ne contient aucun bouton de publication ; il gère connexion/sync/notifications.
- `getSuggestedPhotos()` construit `/community-manager/studio/draft/${publicationId}/suggested-photos` (`sportApi.js:298-300`) ; `null` devient littéralement `null` dans l’URL alors que la route exige `publication_id: int` (`community_manager.py:571-575`).

### 4.6 Comptes, config Meta et sécurité relative

- `GET/PUT /admin/settings/meta` (`:199-258`) exposent `app_id`, `app_secret_configured`, `redirect_uri`, `config_id`, `access_token_configured`, `client_business_id`, `instagram_user_id`, `facebook_page_id`. Secrets chiffrés, jamais renvoyés en clair ; champs vides ne remplacent pas un secret existant.
- `POST /admin/settings/meta/test` (`:261-530`) diagnostique credentials/token/`/me`/comptes assignés sans publier. `POST /admin/settings/meta/debug-token` (`:533-606`) retourne scopes et expiration.
- Unified Login : `/sport/publications/meta/auth` (`:220-228`), `/meta/preflight` (`:231-329`), `/meta/status` (`:332-339`), `DELETE /meta` (`:342-350`), callback public protégé par `state` (`:43-46,378-473`).
- Aucun champ pour activer Story Facebook ni pour configurer un worker de planification. Le contexte Facebook réutilise le champ `instagram_business_account_id` pour stocker le page id (`sport_instagram_publish.py:695-700`).
- Route `/studio/draft/{id}/regenerate` (`community_manager.py:1621-1629`) n’applique pas le filtre d’appartenance athlète présent ailleurs (`sport_publications.py:540-547`).

### 4.7 Erreurs, états vides, responsive, tests

- Erreurs UI : `.publisher-alert` (`CommunityPublisherPage.js:850-855,897-904`) ; `.alert` calendrier avec `scrollIntoView` (`CommunityManagerCalendarPage.js:279-285,415`) ; états vides musique (`PublisherMusicStep.js:200-202`) et recherche (`PublisherMusicStep.js:157`).
- Responsive : media queries présentes dans `app.css:10032-10120`, `publisher.css:2186-2315`, `story-editor.css:747-890` ; test `studio_page.test.mjs` vérifie statiquement `dvh`, `min-height:0` et `overflow` sur la modale.
- Liens/boutons : `rescheduleSuggestion` et `regenerateCommunityManagerHashtags` ont des handlers/méthodes mais aucun bouton rendu ; le bouton « Accepter » déclenche `_openEntry`.
- Tests backend exécutés : 183 passés / 12 échecs. Échecs :
  - `test_studio_caption_sync.py::...test_feed_preview_sets_explicit_dark_text_color` attend `color: #111827` alors que le code produit `color: var(--color-text-primary, #111827)` (`studio.py:1391,1428,1451`).
  - `test_v3_publish.py::...test_validate_empty_content_fails` attend une erreur sur contenu vide ; le code autorise une publication sportive avec titre/hashtags (`studio.py:1284`).
  - 2 tests `TestPublishAPI` appellent `publish_draft()` sans `background_tasks` alors que la signature actuelle l’exige (`community_manager.py:694-698`).
  - 8 tests `TestInstagramCaptionLength` échouent sur `_sport_stats_from_activity()` avec un `AsyncMock` (`studio.py:273`, `:1518`) avant d’atteindre la limite de légende.
- Tests frontend exécutés : 11 suites passent (`community_publisher_page`, `composer_instagram_ux`, `publisher_music_step`, `publisher_preview`, `publisher_story_media_transmission`, `publisher_store`, `story_publish_pipeline`, `studio_page`, etc.) ; 10 échecs de harness/fichiers obsolètes.
- Trous de tests : calendar page, publication standalone, Facebook/both via Studio, scheduler, carousel Meta, handler `story_slide_publish`, reprise `failed`, permissions, responsive navigateur.

---

## 5. Anomalies priorisées

Chaque anomalie est documentée avec : description → reproduction → cause technique → fichiers → correction recommandée → tests nécessaires. Aucune correction n’a été appliquée.

### P0 — Bloquantes

#### A01 — Publication standalone impossible depuis un brouillon local

- **Description :** l’utilisateur peut composer, sauvegarder puis cliquer sur « Publier maintenant » ; la publication échoue avec « Aucun brouillon ».
- **Reproduction :** ouvrir `/publisher/post` (ou « ＋ Créer une publication » dans le calendrier) → sélectionner une photo → saisir une légende → « Brouillon » (toast « Brouillon sauvegardé localement ») → « Publier maintenant ».
- **Cause :** `createBlank()` fixe `currentDraftId = null` (`publisherDraftService.js:100-107`) ; `_saveDraft()` ne persiste que le store (`CommunityPublisherPage.js:799-817`) ; `publish()` exige un ID serveur (`publisherDraftService.js:355-356`).
- **Fichiers :** `app-erp.js:365-373`, `CommunityPublisherPage.js:111-123,799-839`, `publisherDraftService.js:100-107,227-255,355-386`.
- **Correction recommandée :** créer un brouillon serveur au premier `save` ou avant `publish` (endpoint dédié « draft manuel » ou entrée calendrier manuelle), puis sauvegarder systématiquement avant publication. Interdire l’affichage du bouton Publier tant qu’aucun ID serveur n’existe, avec un message explicite.
- **Tests nécessaires :** test d’intégration `createBlank → save → publish` ; test UI sur `/publisher` et sur le bouton calendrier ; test de non-régression sur brouillon serveur existant.

### P1 — À corriger avant mise à disposition

#### A02 — `publication_id` passé comme `calendar_entry_id` depuis le calendrier

- **Description :** après création du Studio draft, le calendrier ouvre Publisher avec l’ID de publication ; Publisher le renvoie au backend comme ID d’entrée de calendrier.
- **Reproduction :** calendrier → clic sur une entrée non Garmin → `createStudioDraftFromCalendar` renvoie `publication_id` → `_openPublisher({ entryId: publication_id })` → `_loadFromCalendarEntry()` → `POST /studio/from-calendar` avec cet ID comme `calendar_entry_id`.
- **Cause :** confusion entre deux identifiants dans la même propriété `entryId`. Backend : recherche `EditorialCalendarEntry.id == data.calendar_entry_id` (`studio.py:617-625`).
- **Fichiers :** `CommunityManagerCalendarPage.js:352-360`, `CommunityPublisherPage.js:183-192`, `publisherDraftService.js:57-70`, `sportApi.js:221-223`, `studio.py:610-655`.
- **Correction recommandée :** conserver `calendarEntryId` et `publicationId` dans deux champs distincts ; ouvrir directement `publisherDraftService.load(publicationId)` après création (`isExistingPublication: true`).
- **Tests nécessaires :** test de l’enchaînement calendrier → création → ouverture ; test backend verify 422 quand l’ID n’existe pas comme entrée ; test UI sans double création.

#### A03 — Photos suggérées Garmin appelées avec `null`

- **Description :** les parcours Garmin construisent `/community-manager/studio/draft/null/suggested-photos`.
- **Reproduction :** calendrier → entrée Garmin, ou MediaPicker → onglet Garmin → sélection d’une activité.
- **Cause :** `getSuggestedPhotos(publicationId, ...)` interpole `null` (`sportApi.js:298-300`) alors que la route exige un entier (`community_manager.py:571-575`). Le résultat est en plus ignoré dans le MediaPicker (`PublisherMediaPicker.js:494-510`).
- **Fichiers :** `CommunityManagerCalendarPage.js:336`, `PublisherMediaPicker.js:496`, `CommunityManagerStudioPage.js:260`, `sportApi.js:298-300`, `community_manager.py:571-581`.
- **Correction recommandée :** exposer un endpoint de suggestions par `activity_id` (ou créer d’abord le brouillon puis utiliser son ID) ; branches UI sur le résultat au lieu de l’ignorer.
- **Tests nécessaires :** test client de l’URL générée ; test endpoint avec `activity_id` ; test E2E Garmin → photos sélectionnées → StoryDraft.

#### A04 — Programmation stockée mais non exécutée et non exposée

- **Description :** `POST /studio/draft/{id}/schedule` met `status=scheduled`, mais aucun worker ne consomme ce statut ; aucun bouton ne permet de planifier.
- **Reproduction :** appeler l’endpoint schedule (ou observer `scheduleStudioDraft` exporté) → la publication reste `scheduled` indéfiniment ; chercher un bouton « Planifier » dans Publisher/Studio → absent.
- **Cause :** `schedule_publication()` écrit seulement la base (`studio.py:1297-1312`) ; `publish_to_instagram()` refuse le statut `scheduled` (`:1920-1921`) ; la boucle jobs ne filtre que `pending/running` (`jobs.py:709-715`) ; `main.py:60-68` ne lance aucun scheduler.
- **Fichiers :** `community_manager.py:541-554`, `studio.py:1297-1312,1920-1921`, `sportApi.js:245-248`, `main.py:60-68,217-247`, `jobs.py:702-823`.
- **Correction recommandée :** soit implémenter un scheduler idempotent qui enfile `community_publish` à `scheduled_at`, soit retirer/désactiver l’endpoint et l’export client tant que la fonction n’est pas prête. Ajouter le sélecteur de date dans Publisher/Studio.
- **Tests nécessaires :** test d’enfilement à échéance, test d’idempotence, test fuseau Europe/Paris, test UI planification.

#### A05 — Carrousel sélectionnable mais publié en photo unique

- **Description :** le format carrousel accepte jusqu’à 10 photos ; la publication n’envoie que `photo_id` (première photo) à Meta.
- **Reproduction :** Publisher carrousel → sélectionner 3 photos → publier → inspecter le payload Meta : un seul `image_url`, aucun `children`.
- **Cause :** `design["carousel"]` est persisté (`studio.py:724-739`) mais `_publish_media_photo_id()` retourne un ID unique (`:1870-1881`) et `create_media_container()` n’a pas de paramètre album (`sport_instagram_publish.py:196-258`).
- **Fichiers :** `publisherStore.js:25-32`, `publisherDraftService.js:236-238`, `studio.py:724-739,1870-1881,1967-2006`, `sport_instagram_publish.py:196-258`.
- **Correction recommandée :** implémenter le container album Meta (`media_type=CAROUSEL`, `children`) et adapter la préparation des URLs signées ; à défaut, bloquer le format carrousel à la publication avec un message clair.
- **Tests nécessaires :** test payload `children` mocké, test 2–10 photos, test échec si >10, test non-régression photo unique.

#### A06 — Stories Facebook / `both` annoncées puis refusées

- **Description :** le schéma de requête commente `instagram, facebook, both`, mais l’endpoint refuse tout sauf Instagram ; le handler force `platform: "instagram"`.
- **Reproduction :** `POST /story-studio/draft/{id}/publish` avec `platforms: ["facebook"]` → 422 « La publication Story est disponible sur Instagram uniquement ».
- **Cause :** contrat de schéma non aligné avec la règle métier et le handler.
- **Fichiers :** `community_manager.py:110-112,1070-1097,1118`, `jobs.py:625-682`.
- **Correction recommandée :** choisir une seule vérité : restreindre le schéma à `["instagram"]` et documenter l’UI, ou implémenter FB/`both` dans le handler et la config Meta.
- **Tests nécessaires :** test de validation du payload, test handler Multi-plateforme si retenu, test UI cohérent.

#### A07 — Musique Story sélectionnée et sauvegardée mais non publiée

- **Description :** l’utilisateur choisit une piste Instagram, l’aperçu l’affiche, le draft la persiste ; le job Story n’envoie aucun paramètre audio à Meta.
- **Reproduction :** Publisher Story → étape Musique → rechercher/sélectionner → sauvegarder → publier → inspecter `publish_story()` : aucun `audio_configuration`.
- **Cause :** `audio_configuration` est bien porté par le pipeline (`publisherDraftService.js:370`, `storyPublishPipeline.js:117-118`, `community_manager.py:888-889`) mais `jobs.py:654-659` appelle `meta_service.publish_story()` sans audio ; `sport_instagram_publish.py:460-478` n’a pas le paramètre. L’UI l’indique honnêtement (`PublisherPreview.js:198`, `PublisherMusicStep.js:212`).
- **Fichiers :** `PublisherMusicStep.js:171-212`, `PublisherPreview.js:195-199`, `publisherDraftService.js:240-242,355-379`, `story_orchestrator.py:504-543`, `jobs.py:654-659`, `sport_instagram_publish.py:460-478`.
- **Correction recommandée :** si Meta prend en charge la musique Story via l’Audio API, câbler le paramètre ; sinon retirer l’étape de sélection ou la présenter comme simple brouillon créatif sans promesse de publication.
- **Tests nécessaires :** test de transmission audio (mock Graph), test d’acceptation réelle Meta, test UI libellé.

#### A08 — Quick publish Garmin incomplet

- **Description :** le bouton 📸 d’une activité ouvre un `post` générique ; ni les photos suggérées ni les statistiques de l’activité ne sont chargées automatiquement.
- **Reproduction :** Sport → activités → 📸 → `/publisher/post?garmin=<id>` → aucune photo pré-sélectionnée, aucun overlay stats ; MediaPicker appelle `getSuggestedPhotos(null, 50)` et ignore le résultat.
- **Cause :** ancien `GarminQuickPublicationView` remplacé par le Publisher unifié sans équivalent ; `setGarmin()` ne stocke que `activityId`.
- **Fichiers :** `SportActivitiesPage.js:20-25`, `app-erp.js:461,466`, `CommunityPublisherPage.js:199-203,875-879`, `PublisherMediaPicker.js:494-510`, `garmin_quick_publication.test.mjs:4`.
- **Correction recommandée :** réimplémenter le quick publish dans le flux unifié : charger photos + stats, créer le brouillon Story/Reel approprié, puis ouvrir Publisher sur ce draft.
- **Tests nécessaires :** test E2E activité → médias → publication ; test non-régression du parcours calendrier Garmin.

#### A09 — Permissions de route et d’action incohérentes

- **Description :** `community_manager.strategy_view` suffit à ouvrir calendrier/Publisher, mais les endpoints Studio exigent `community_manager.calendar_generate`. Les boutons de génération sont masqués, pas l’ouverture d’une entrée qui crée un brouillon.
- **Reproduction :** utilisateur avec `strategy_view` seul → ouvrir `/community-manager` → clic sur une entrée → appel `POST /studio/from-calendar` susceptible d’être refusé 403.
- **Cause :** élargissement de la permission de route sans alignement des permissions d’action.
- **Fichiers :** `app-erp.js:359-361,365-373`, `CommunityManagerCalendarPage.js:79-80,315-360`, `community_manager.py:123-176,293-312`.
- **Correction recommandée :** soit durcir les routes au niveau d’action requis, soit basculer les endpoints en permissions de lecture cohérentes avec le parcours ; définir une matrice RBAC explicite.
- **Tests nécessaires :** tests paramétrés par rôle sur routes + endpoints ; test UI masquage/désactivation cohérent.

#### A10 — Suites de tests rouges : confiance de release insuffisante

- **Description :** 12 tests backend et 10 suites frontend échouent dans l’état courant.
- **Reproduction :** commandes de la section 1.2.
- **Cause :** tests non alignés avec les signatures/le comportement actuel (`publish_draft(background_tasks)`, `_ensure_sport_defaults`, preview CSS var, validation sport), harness Node/Windows, fichier Garmin supprimé.
- **Fichiers :** `tests/community_manager/test_v3_publish.py:1600,1689,1710,1902-2061`, `tests/community_manager/test_studio_caption_sync.py:283`, `tests/frontend/editor_*.test.mjs`, `tests/frontend/garmin_quick_publication.test.mjs:4`.
- **Correction recommandée :** triage test par test : mettre à jour les attentes légitimes, corriger les régressions réelles, réparer le harness ESM, supprimer/remplacer les tests obsolètes. Ajouter un script npm `test` unique.
- **Tests nécessaires :** cible 100 % vert sur les suites CM avant correction fonctionnelle ; jeu de non-régression sur les 12 échecs.

### P2 — Importantes

#### A11 — Sélecteur de compte Instagram sans effet persistant

- **Description :** `accountId` est mis dans le store mais jamais envoyé au serveur ; les synchronisations API remettent `accountId: null`.
- **Reproduction :** Publisher → légende → choisir un compte → sauvegarder → rouvrir : la sélection n’est plus durable ; la publication utilise le compte configuré côté Meta.
- **Cause :** `publisherDraftService.save()` n’envoie que title/content/hashtags/photo_ids/design/audio (`publisherDraftService.js:231-242`) ; `_syncStoreFromStudio/Story` fixent `accountId: null` (`:177,214`).
- **Fichiers :** `PublisherCaptionEditor.js:440-445`, `publisherDraftService.js:174-184,210-221,231-242`, `CommunityPublisherPage.js:574-577`.
- **Correction recommandée :** transporter l’ID de compte jusqu’au service de publication ou retirer le sélecteur si le backend impose le compte unique (Unified Login).
- **Tests nécessaires :** test de persistance aller-retour ; test de publication avec compte choisi.

#### A12 — Bouton « Accepter » déclenche création de brouillon et ouverture Publisher

- **Description :** l’action rapide ✓ ne fait pas seulement accepter la suggestion ; elle exécute `_openEntry` complet.
- **Reproduction :** calendrier → suggestion en attente → clic sur ✓ → acceptation + passage `planifié` + création Studio draft + remplacement du calendrier par Publisher.
- **Cause :** réutilisation du handler d’ouverture (`CommunityManagerCalendarPage.js:596-601`).
- **Correction recommandée :** appeler directement `acceptSuggestion(entryId)` et rafraîchir le calendrier ; garder l’ouverture Publisher sur le clic sur la carte uniquement.
- **Tests nécessaires :** test unitaire du handler ✓ ; test E2E sans changement de vue.

#### A13 — Boutons inopérants / absents : report et régénération hashtags

- **Description :** `_rescheduleSuggestion()` n’est appelé nulle part ; un handler `[data-action="regenerate-hashtags"]` est enregistré mais aucun bouton ne porte cet attribut.
- **Reproduction :** observer les entrées du calendrier : seulement Accepter / Refuser / Supprimer.
- **Cause :** refonte du calendrier sans recâblage ni nettoyage.
- **Fichiers :** `CommunityManagerCalendarPage.js:184-217,483-518,565-627`.
- **Correction recommandée :** ajouter les boutons et leurs états de chargement, ou retirer le code mort et documenter la non-disponibilité.
- **Tests nécessaires :** tests DOM des boutons + appels API correspondants.

#### A14 — Normalisation fragile des IDs médias

- **Description :** tout ID qui n’est pas `photo_<entier>` est filtré silencieusement lors de la sauvegarde.
- **Reproduction :** injecter un média `media_<timestamp>` via `preselectedMedia` (`CommunityPublisherPage.js:127-131`) puis sauvegarder : `photo_ids` devient vide.
- **Cause :** `parseInt(m.id.replace('photo_', ''))` + filtre `isNaN` (`publisherDraftService.js:236-238`).
- **Correction recommandée :** conserver un `photoId` numérique explicite dans le store et l’envoyer au lieu de parser l’ID d’affichage ; lever une erreur visible si un média n’a pas d’ID serveur.
- **Tests nécessaires :** test avec IDs `photo_11`, `11`, `local_x`, `media_x`.

#### A15 — `publish_to_both` marque un succès partiel comme partagé

- **Description :** si une seule plateforme réussit, `pub.status = "shared"` et l’entrée de calendrier passe à `publié`.
- **Reproduction :** mock IG en échec, FB en succès → statut local `shared`, `error_message = "Publication partielle - Instagram: ..."`.
- **Cause :** agrégation « au moins une plateforme » (`studio.py:2394-2417`).
- **Correction recommandée :** distinguer `shared_partial` ou conserver `failed` avec résultats détaillés ; ne pas marquer le calendrier « publié » que si toutes les cibles demandées ont réussi.
- **Tests nécessaires :** matrice 4 cas (succès/succès, IG seul, FB seul, échec complet) + état calendrier.

#### A16 — Jobs CM dépendants du module Photos

- **Description :** la boucle qui traite `community_publish` n’est créée que si `PHOTO_ENABLED` est vrai.
- **Reproduction :** désactiver le module Photos → publier via CM → job reste `pending`.
- **Cause :** réutilisation de `_photo_job_loop` pour les jobs CM (`main.py:66-67,217-247`).
- **Correction recommandée :** découpler l’ordonnanceur des jobs CM du module Photos ou documenter la dépendance comme prérequis obligatoire.
- **Tests nécessaires :** test de démarrage avec `PHOTO_ENABLED=false` + job CM.

#### A17 — `job_id` manquant dans le payload de rendu Story

- **Description :** le handler de rendu attend `payload["job_id"]` pour retrouver la slide et mettre à jour `render_jobs`, mais l’API ne l’ajoute pas au payload.
- **Reproduction :** `POST /story-studio/draft/{id}/render-slide/{index}` → handler `_studio_render` → lecture de `job_id` absent.
- **Cause :** décalage entre enqueue (`community_manager.py:957-968`) et handler (`jobs.py:537,583-597`).
- **Correction recommandée :** transmettre le `job_id` retourné par `enqueue_job` ou utiliser `slide_index` de manière consistante des deux côtés.
- **Tests nécessaires :** test handler avec payload réel ; test progression `render_jobs` et `output_path`.

#### A18 — Doublon `FORMAT_CONFIG` et dérive potentielle

- **Description :** la configuration des formats est déclarée deux fois ; les copies sont identiques aujourd’hui, `post` et `carousel` partagent les mêmes étapes.
- **Cause :** contournement des tests qui suppriment les imports (`publisherStore.js:12-14`, `CommunityPublisherPage.js:41-43`).
- **Correction recommandée :** injecter la config dans les tests plutôt que de supprimer les imports ; garder une seule source de vérité. Vérifier que l’égalité `post`/`carousel` est bien voulue.
- **Tests nécessaires :** test d’égalité entre les deux tables ; test d’injection de dépendance.

#### A19 — Pages héritées non routées / test obsolète

- **Description :** `CommunityManagerPage.js`, `CommunityManagerStudioPage.js` et le test `garmin_quick_publication.test.mjs` portent sur un ancien parcours non atteignable.
- **Cause :** migrations successives sans nettoyage.
- **Correction recommandée :** archiver ou supprimer après validation produit ; aligner la suite de tests sur le routage réel.
- **Tests nécessaires :** test de couverture route ↔ composant.

#### A20 — Route de régénération sans filtre d’appartenance

- **Description :** `POST /studio/draft/{id}/regenerate` récupère l’activité par ID sans le contrôle d’athlète appliqué ailleurs.
- **Cause :** appel direct au service Garmin (`community_manager.py:1621-1629`, `garmin.py:306-310`) au lieu du chemin contrôlé (`sport_publications.py:540-547`).
- **Correction recommandée :** appliquer le même filtre d’appartenance que `get_publication`.
- **Tests nécessaires :** test multi-utilisateurs (accès refusé sur publication d’autrui).

### P3 — Qualité / dette

#### A21 — `TypeError` non bloquant sur le bouton Suivant

- **Description :** `_navLock()` retourne `undefined` ; le `.catch()` du handler plante en console.
- **Reproduction :** clic Suivant sur une étape avec sauvegarde Compose ; navigation correcte mais erreur console.
- **Cause :** `CommunityPublisherPage.js:658-660` vs `:672-685`.
- **Correction recommandée :** retourner la promesse de `_navLock`.
- **Tests nécessaires :** test zéro erreur console sur parcours complet.

#### A22 — Détection d’extension vidéo inefficace sur les URL signées

- **Description :** les URL `PUBLIC_URL/photos/{id}/file?...` n’ont pas d’extension ; le service retombe sur `"photo"` et seule la validation MIME corrige le tir.
- **Cause :** `_detect_media_type_from_url` (`sport_instagram_publish.py:157-170`) conçu pour des URL à extension.
- **Correction recommandée :** transmettre explicitement le `mime_type`/`is_video` au constructeur de container.
- **Tests nécessaires :** test URL sans extension + MIME vidéo.

#### A23 — Page Facebook stockée dans le champ Instagram

- **Description :** `resolve_facebook_publish_context()` réutilise `instagram_business_account_id` pour stocker le page id.
- **Cause :** compatibilité de structure `_MetaConfigContext` (`sport_instagram_publish.py:661-701`).
- **Correction recommandée :** champ dédié `facebook_page_id` dans le contexte ; migrer les lectures.
- **Tests nécessaires :** tests de résolution de contexte IG et FB isolés.

#### A24 — Libellés et scripts E2E non exécutés en conditions réelles

- **Description :** les scripts `e2e_music_workflow.mjs` et `e2e_step_restore.mjs` mockent les API et exigent un navigateur externe absent ; ils ne prouvent ni l’UI réelle ni Meta.
- **Correction recommandée :** intégrer ces scénarios dans une CI avec serveur + navigateur, ajouter un jeu de tests Meta en bac à sable.
- **Tests nécessaires :** exécution CI desktop/mobile ; validation Meta contrôlée avec comptes de test.

---

## 6. Plan de correction proposé (lots)

> Aucun lot n’est démarré. Ordre recommandé : débloquer le parcours de création, puis fiabiliser les intégrations, puis nettoyer la dette.

| Lot | Objectif | Anomalies | Critère de sortie |
|---|---|---|---|
| **Lot 0 — Parcours de création publiable** | Rendre la publication standalone et la création depuis calendrier cohérentes | A01, A02, A03, A14 | `/publisher/post` et « Créer une publication » produisent un draft serveur et publient ; aucun ID publication passé comme entrée ; suggestions Garmin retournent des photos. |
| **Lot 1 — Programmation et formats** | Ne pas annoncer ce qui ne fonctionne pas | A04, A05, A06, A07 | Scheduler réel ou fonction désactivée ; carrousel publié en album ou bloqué ; contrat Stories unique ; musique Story câblée ou retirée. |
| **Lot 2 — Garmin et calendrier** | Restaurer les actions attendues | A08, A09, A12, A13 | Quick publish Garmin charge photos/stats ; ✓ accepte sans changer de vue ; report et régénération hashtags exposés ou retirés ; RBAC cohérent. |
| **Lot 3 — Meta / publication multi-plateforme** | Fiabiliser FB, both, jobs et statuts | A15, A16, A17, A20, A22, A23 | Statut partiel explicite ; jobs CM indépendants de Photos ; rendu Story suivi ; filtre athlète ; mime explicite ; contexte FB dédié. |
| **Lot 4 — Qualité & validation** | Rendre la suite de tests verte et représentative | A10, A18, A19, A21, A24 | 100 % des suites CM vertes ; script `npm test` ; E2E exécutés desktop/mobile ; validation Meta en bac à sable documentée. |

### 6.1 Tests de non-régression obligatoires avant livraison

1. `pytest tests/community_manager tests/test_ig_music.py tests/test_meta_config_publish.py tests/test_meta_story_publish.py tests/test_studio_story_flow.py tests/test_calendar_suggestions.py -q` → 0 échec, sans stub externe (dépendance `PyJWT` réparée).
2. `node --test` sur les suites Publisher/Music/Story/Studio/Garmin → 0 échec, harness Windows corrigé.
3. Scénarios E2E navigateur (desktop 1440×900, mobile 390×844) sur : calendrier, création standalone, publication depuis calendrier, Story + musique, Reel + musique, Facebook, both, programmation.
4. Matrice Meta en environnement de test : photo IG, Reel + `audio_configuration`, Story JPEG, photo FB, both avec échec partiel simulé.
5. Contrôle RBAC complet : `strategy_view` seul, `calendar_generate`, `settings_update`.

---

## 7. Ce qui reste à valider par l’humain / le coordinateur

- **Propriétaire du module :** confirmer la priorisation P0/P1, arbitrer les choix produit pour A05 (album vs blocage), A06 (Story FB ou Instagram-only), A07 (musique Story câblée ou retirée), A04 (scheduler ou retrait), A09 (matrice RBAC).
- **Coordinateur :** vérifier croisément les preuves A01–A10, notamment l’interprétation du mismatch d’ID (A02) et l’absence de scheduler (A04), avant de prononcer la conclusion définitive.
- **Validation métier :** définir les comptes Meta de test et le périmètre autorisé pour une validation réelle sans toucher à la production.
- **Aucune correction ne doit être engagée avant ces validations.**

---

## Annexe A — Fichiers consultés (principaux)

- `app/api/community_manager.py`, `app/api/admin.py`, `app/api/sport_publications.py`, `app/main.py`
- `app/services/community_manager/{studio,service,ig_music}.py`
- `app/services/{story_orchestrator,sport_instagram_publish,sport_media_publish}.py`
- `app/services/photo/jobs.py`, `app/services/sport_publications.py`
- `app/modules/community_manager.py`, `app/schemas/{admin,sport}.py`, `app/core/config.py`
- `src/public/js/app-erp.js`, `src/public/js/pages/{CommunityManagerCalendarPage,CommunityPublisherPage,CommunityManagerPage,CommunityManagerStudioPage,StoryStudioPage,SportActivitiesPage,UserSettingsPage}.js`
- `src/public/js/components/{PublisherMediaPicker,PublisherMusicStep,PublisherPreview,PublisherCaptionEditor,NavItem,Sidebar}.js`
- `src/public/js/stores/publisherStore.js`, `src/public/js/services/{publisherDraftService,sportApi,storyPublishPipeline,adminApi}.js`
- `src/public/js/editors/{PublisherStoryEditor,PublisherReelEditor}.js`, `src/public/js/editor/StoryEditorView.js`
- `src/public/css/{app,publisher,story-editor}.css`
- `tests/community_manager/*`, `tests/frontend/*`, `tests/test_*.py` liés à Meta/IG/FB/calendrier
- `e2e_music_workflow.mjs`, `e2e_step_restore.mjs`

**Fin du rapport.**
