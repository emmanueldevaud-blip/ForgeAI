# Sport Editorial Engine V2

Le moteur éditorial sportif est un service métier indépendant des plateformes.

## Flux

`EditorialCalendarEntry` → activité Garmin source → `build_editorial_brief()` →
direction artistique → génération IA existante → `SportPublication.design` →
renderer Studio/FFmpeg → validation humaine → publication Meta existante.

## Données produites

Le brief contient l'analyse de l'activité, la direction (`humour`, `aventure`,
`performance` ou `souvenir`), le template graphique, les hashtags et une mémoire
légère des publications récentes. Il est exposé par
`GET /community-manager/studio/draft/{id}/editorial-brief`.

Les données manquantes restent absentes : le moteur ne déduit pas de lieu,
d'émotion ou de performance sans source Garmin ou photo exploitable.

## Rendu

Le renderer Studio existant est conservé. Le style mémorisé modifie uniquement
la palette de l'overlay, tandis que le format, le cadrage, l'audio et l'encodage
restent centralisés dans Studio/FFmpeg.
