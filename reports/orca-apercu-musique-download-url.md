# Aperçu musical — cause du « boutons présents mais écoute muette »

Date : 2026-11-27. Correctif non commité à ce stade. Suite au commit `ebff704`.

## Signal

« Ok en musique j’ai bien les bouton mais l’écoute ne fonctionne pas. »

## Cause

Le doc Meta Instagram Audio API distingue deux champs :

- `download_url` : URL temporaire du **fichier audio** lisible par `<audio>` (expire après ~1,5 jour) ;
- `on_platform_audio_preview_link` : URL d’une **page instagram.com**, pas un flux audio.

Le code healait `preview_link` depuis `on_platform_audio_preview_link` et le front tentait de lire cette page HTML dans un lecteur audio. Résultat : bouton `▶` affiché, puis `error`/`play()` rejeté et message « Aperçu audio indisponible ».

## Correctif

- `app/services/community_manager/ig_music.py`
  - `normalize_audio_result()` : `preview_link` = `download_url` (ou équivalent audio), `platform_preview_link` = lien Instagram séparé ;
  - `search_ig_audio()` normalise tous les résultats `/ig_audio` ;
  - `pick_audio_for_photo()` / `pick_audio_for_photos()` persistent la même séparation.
- `app/api/community_manager.py`
  - `/studio/draft/{id}/audio-proposals` et `/story-studio/draft/{id}/audio-proposals` ne renvoient plus une page Instagram comme `preview_link`.
- `src/public/js/components/PublisherMusicStep.js?v=5`
  - `previewUrlFor()` lit `download_url` en priorité et refuse explicitement les hôtes `instagram.com` comme source audio.
- Tests frontend T4/T4b et backend `test_story_audio_proposals.py` mis à jour (5 tests verts).

## Vérification navigateur (vrai lecteur, 1180×820 tactile)

Mock de recherche avec `download_url: /music/calm-piano.mp3` + `on_platform_audio_preview_link` Instagram :

| Contrôle | Résultat |
| --- | --- |
| Bouton `▶` rendu | oui |
| Après tap | `src = http://localhost:8000/music/calm-piano.mp3` |
| Lecture réelle | `paused = false`, `currentTime = 11.08 s`, `duration = 120 s` |
| `aria-pressed` | `true` |
| Second tap | lecteur arrêté, `aria-pressed = false` |
| `draft.music` | inchangé (aucune URL écrite) |

Suite frontend : 14 vertes / 23, 9 échecs `editor_*` préexistants inchangés.
`.venv\Scripts\python.exe -m pytest tests/test_story_audio_proposals.py -q` : 5 passés.
`git diff --check` vert. Limite conservée : `download_url` expire (~1,5 jour) ; une nouvelle recherche/ouverture d’étape en génère une fraîche.
