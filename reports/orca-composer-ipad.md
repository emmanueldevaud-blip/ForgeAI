# Composer iPad — diagnostic et correctif (non commité)

Date : 2026-11-27. Périmètre : `master` local, aucun commit/push sans autorisation.

## Signal

« En mode iPhone le composer fonctionne bien. En mode pc aussi mais pas en mode iPad. »

## Reproduction (navigateur Orca, vrai CSS v31 + vrai composant)

| Vue | Règles actives | Symptôme avant correction |
| --- | --- | --- |
| iPhone 390×844, tactile | mobile | OK (référence) |
| iPad 820×1180, tactile | mobile + `min-width:768` | OK |
| iPad 768×1024, tactile | mobile + `min-width:768` | OK |
| iPad 1180×820, tactile | mobile **+ PC** | `.pmc-panel` absolu 124×562 par-dessus la photo, `overlap=true`, `composer.scrollH 570 > clientH 562` |
| iPad 1024×768, tactile | mobile **+ PC** | même chevauchement |
| iPad Pro 1024×1366, tactile | mobile **+ PC** | même chevauchement |
| PC 1366×768 / 1440×900 | PC | OK (référence) |

Cause : `@media (hover: none), (max-width: 899px)` (mobile, panneau en absolu) et
`@media (min-width: 900px) and (min-height: 620px)` (grille PC) s'appliquaient
simultanément sur les iPad larges. Le bloc PC, postérieur, passait le composer en
`display:grid` mais n'effaçait ni `position:absolute`, ni `top:8px`, ni
`transform:translateX(-50%)` du panneau.

## Correctif

- `src/public/css/publisher.css` : bloc mobile limité à `@media (max-width: 899px)` ;
  les tablettes tactiles ≥900 px utilisent uniquement la grille PC.
- Bloc ajouté après la grille PC :
  `@media (min-width: 900px) and (min-height: 620px) and (hover: none)` avec cibles
  tactiles élargies (`Aa`/`☺` 44 px, actions de calque 40 px, poignées 36–40 px).
- `src/public/index.html` : `publisher.css?v=32`.
- `tests/frontend/composer_instagram_ux.test.mjs` : garde-fou des deux media queries,
  de leur ordre dans la cascade et de la version CSS.

## Vérifications après correction

| Vue | Résultat |
| --- | --- |
| iPad 1180×820 | `display:grid`, `panel static 300×538`, `stage 297×528`, `overlap=false`, `scrollH=clientH` |
| iPad 1024×768 | `panel static 300×486`, `stage 268×476`, `overlap=false` |
| iPad Pro 1024×1366 | `panel static 300×1084`, `stage 368×1074`, `overlap=false` |
| iPad 820×1180 / 768×1024 | mise en page mobile inchangée, `overlap=false` |
| iPhone 390×844 | inchangé (panneau superposé voulu, aucun débordement horizontal) |
| PC 1366×768 / 1440×900 | inchangé |

Cibles iPad en grille PC : `.pmc-tool-btn` 44×44, `.pmc-overlay-btn` 40×40,
`.pmc-panel` `position:static`.

Tests : `composer_instagram_ux`, `publisher_minimal_composer` (23/23),
`publisher_music_step` (T8), `publisher_layout` verts ; suite frontend complète
14 vertes / 23 avec les 9 échecs `editor_*` préexistants inchangés ;
`git diff --check` vert. Aucun secret, déploiement, production, publication Meta,
`.env`, port 8000 ni base modifiés.
