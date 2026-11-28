# Déclenchement IA musique juste après la sélection (Story)

Date : 2026-11-28. Correctif non commité à ce stade. Suite au feu vert « Ok vas y ».

## Signal

« En parallèle, la proposition de musique via ia à partir de la photo sélectionné ne fonctionne pas. Prévoit de déclencher le processus juste après près la sélection en arrière plan pour moins de latence »

## Cause

- La présélection IA ne partait que depuis l’ouverture de l’étape Musique (`PublisherMusicStep._suggestInitialMusic`).
- Elle reposait sur le brouillon serveur Story (`selected_asset_ids`) via `GET /story-studio/draft/{id}/audio-proposals`.
- Pour une Story créée par sélection (MediaPicker → libellé « Nouvelle publication »), le brouillon serveur n’existe pas encore au moment de la sélection : la proposition arrivait vide ou sans contexte photo.

## Correctif

- `src/public/js/services/sportApi.js`
  - `getStoryAudioProposals(draftId, photoIds = [])` : accepte des `photo_ids` optionnels.
  - Nouveau `getStoryAudioForPhotos(photoIds, title, hashtags)` → `GET /community-manager/story/photos/audio-proposals?photo_ids=…`.
- `app/api/community_manager.py`
  - Nouvel endpoint léger `GET /story/photos/audio-proposals` (photo_ids explicites, sans brouillon).
  - `GET /story-studio/draft/{draft_id}/audio-proposals` accepte `photo_ids` optionnels (prioritaires sur le brouillon).
  - Refactor partagé `_story_audio_proposals_response()` (analyse IA + repli catalogue).
- `src/public/js/components/PublisherMusicStep.js?v=6` (import `sportApi.js?v=18`)
  - `suggestForPhotoIds(photoIds)` : présélection IA sur photos explicites, en arrière-plan.
  - `_requestSuggestion(draftId, photoIds)` : orchestration (brouillon ou photos), avec garde-fous.
- `src/public/js/pages/CommunityPublisherPage.js` (MusicStep `?v=6`)
  - `onSelectionChange` du MediaPicker câblé → `_onMediaSelectionChange(ids)`.
  - Pour une Story : déclenchement direct si l’étape Musique est montée, sinon mémorisation (`_pendingStoryMusicPhotoIds`) puis consommation à l’ouverture de l’étape.

## Comportements préservés

- Format ≠ Story : aucun déclenchement.
- Choix explicite (`music.cleared`) ou sélection déjà résolue : pas d’écrasement.
- Sélection déjà auto-présélectionnée (`_autoSelected`) : pas de re-déclenchement.
- A07 : la piste reste un brouillon créatif (aucune écriture dans `design.ig_audio`, aucune publication).

## Vérification

- `node tests/frontend/publisher_music_step.test.mjs` : T8 + nouveau T8b OK.
- `node tests/frontend/composer_instagram_ux.test.mjs` : OK (versions v6/v18 en place).
- `node tests/frontend/community_publisher_page.test.mjs`, `publisher_preview`, `publisher_media_picker`, `lot0_*`, `lot1_formats`, `story_publish_pipeline`, `publisher_minimal_composer`, `publisher_creation_tools`, `studio_page`, `publisher_layout` : OK.
- Backend : `python -m py_compile app/api/community_manager.py` OK (runtime sans fastapi/pytest).
- `git diff --check` : vert.

## État

Correctif livré en local (non commité). Livraison Git attendue : feu vert explicite du propriétaire avant commit.
