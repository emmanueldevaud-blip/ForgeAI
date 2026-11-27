# Composer iPad — saisie tactile et aperçu musical (non commité)

Date : 2026-11-27. Périmètre : `master` local, aucun commit/push sans autorisation.
Suite au correctif de mise en page iPad livré dans `f37948e`.

## Signal

- « En mode iPad, l’écriture d’un text et la page composer ne fonctionne pas. »
- Précision du propriétaire : « Tap sur le texte ne permet pas d’écrire ».
- « Prévois une possibilité d’écouter les musique à la selection. »

## 1. Saisie directe sur le texte (iPad)

### Diagnostic

La mise en page est désormais correcte (grille PC + cibles tactiles au-delà de 899 px),
mais le tap direct sur un calque `contenteditable` ne garantissait pas l’ouverture
du clavier sur iPad Safari. Le seul chemin fiable passait par le bouton `Aa`, qui
appelait `_focusLayer()` dans un geste explicite.

### Correctif

- `PublisherMinimalComposer.js` :
  - helper `isTouchLayout()` (`(hover: none), (max-width: 899px)`), réutilisé par
    le tap sur le fond et par la saisie ;
  - `pointerdown` sur chaque calque texte : focus explicite dans le geste tactile,
    sauf sur les poignées de déplacement/rotation et tant que le calque est vide
    et que `Aa` n’a pas été tapé ;
  - `click` : sélection du calque puis focus de nouveau sur les layouts tactiles ;
  - le focus est conservé : aucun `_render()` n’est déclenché par ce chemin.
- `publisher.css` :
  - `-webkit-user-select: text` sur `.pmc-overlay` (Safari iPad) ;
  - `min-height: 44px` sur `.pmc-overlay` dans le bloc tactile ≥ 900 px pour
    élargir la cible du doigt.
- Versions : `publisher.css?v=33`, `PublisherMinimalComposer.js?v=16`.

## 2. Aperçu musical à la sélection

### Comportement

- Chaque résultat de recherche qui expose une URL d’aperçu (`preview_link`,
  `preview_url`, `on_platform_audio_preview_link`, `on_platform_audio_preview_url`)
  affiche un bouton `▶` permettant d’écouter avant de choisir.
- Après sélection (y compris présélection IA), un bouton `▶ Écouter` est affiché
  dans la piste sélectionnée. Un second tap arrête la lecture.
- Les URL sont validées (`http:` / `https:` uniquement) ; sans URL exploitable,
  aucun bouton n’apparaît et un message « Aperçu audio indisponible » est affiché
  si l’utilisateur tente tout de même d’écouter.
- La lecture utilise un élément `<audio>` créé à la volée. L’URL reste uniquement
  dans une `Map` du composant : elle n’est **jamais** écrite dans `draft.music`,
  `audio_configuration`, `design.ig_audio` ni envoyée à `publish()` (A07 reste un
  brouillon créatif, aucune piste intégrable à la publication Story).
- Versions : `PublisherMusicStep.js?v=4`, imports page/aperçu mis à jour.

## Vérifications

Navigateur Orca, vrai CSS/composants, viewport 1180×820 tactile :

| Contrôle | Résultat |
| --- | --- |
| `matchMedia('(hover: none), (max-width: 899px)')` | `true` |
| Tap direct (`pointerdown` touch) sur le texte | `activeElement = DIV[data-pmc-layer-text="0"]`, `isContentEditable = true` |
| Cible texte | `min-height = 44px`, `user-select = text` |
| Résultats de recherche avec `preview_link` | bouton `data-music-preview` présent |
| Tap aperçu | `<audio>` créé, `src = https://audio.example/preview.mp3`, `aria-pressed = true` |
| Brouillon après lecture | `draft.music` inchangé (`trackId: null`) |

Tests : `composer_instagram_ux`, `publisher_minimal_composer` (23/23),
`publisher_music_step` (T1–T8, dont T4b aperçu), `publisher_layout` verts ;
suite frontend complète 14 vertes / 23 avec les 9 échecs `editor_*` préexistants
inchangés ; `git diff --check` vert.

Aucun secret, `.env`, déploiement, production, publication Meta, port 8000,
base ou commit/push. En attente d’autorisation pour livraison.
