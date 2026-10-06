# Agent Sport — Coach autonome

> **Classification : assistant automatisé.** L'agent observe les données d'un athlète,
> décide lui-même (via l'AI Gateway et un jeu d'outils contrôlés par RBAC), agit,
> vérifie le résultat en base puis réévalue avant de conclure.
>
> **Activé par défaut** (`SPORT_AGENT_ENABLED=true`). Positionner la variable à
> `false` pour retomber purement et simplement sur les jobs historiques (aucun
> chemin existant n'est alors modifié). Une analyse non produite par l'agent est
> toujours rattrapée par le job historique (`ensure_ready` du cycle).

---

## Architecture

```
déclencheur (cycle 60 s / Assistant IA)
        │
        ▼
app/services/sport_agent/triggers.py      run_agent_trigger()
        │                                   └─ drapeau + catalogue de triggers
        ▼
app/services/sport_agent/agent.py         SportAgent.run()
        │                                   └─ crée SportAgentExecution (trace durable)
        ▼
app/services/sport_agent/orchestrator.py  AgentOrchestrator.execute()
        │
        ├─ OBSERVE   brief déterministe : objectifs, comptes de recommandations,
        │            recommandations actives (avec état à la création), contexte
        │            de récupération, dernière exécution, payload du déclencheur
        ├─ DECIDE    AI Gateway + outils → décision JSON du modèle
        ├─ ACT       exécution des actions (registre → RBAC → service)
        ├─ VERIFY    relecture en base de chaque cible (recommandation,
        │            notification, analyses générées)
        └─ REASSESS  follow_up ? → nouveau tour, sinon conclusion
        │
        ▼
SportAgentExecution (status, step_count, steps_json, result_json)
```

### Boucle réelle

1. **OBSERVE** — aucun appel IA : un brief est construit par requêtes SQL (objectifs
   actifs, comptes de recommandations par statut, recommandations actives avec
   l'état de l'athlète à leur création, contexte de récupération, dernière
   exécution, payload).
2. **DECIDE** — la mission + le brief partent à l'AI Gateway avec la liste des outils
   (`build_tool_instructions`). Le modèle appelle les outils jusqu'à rendre sa décision.
3. **ACT** — les `actions` de la décision sont exécutées via le registre (mêmes
   vérifications de permission que n'importe quel code applicatif).
4. **VERIFY** — chaque cible est relue en base : `verified` vaut `True` (confirmé),
   `False` (échec) ou `None` (non vérifiable). Les outils `generate_*` sont
   vérifiés de la même façon (ligne `SportAnalysis` présente et appartenant à
   l'athlète) : une analyse annoncée « créée » mais absente de la base ne compte
   pas dans `created_analyses` et ne bloque donc pas le repli historique.
5. **REASSESS** — `follow_up=true` relance un tour ; une vérification échouée n'autorise
   qu'un tour de retry forcé.

### Garde-fous

| Garde | Réglage / valeur | Comportement |
|---|---|---|
| Étapes de décision | `SPORT_AGENT_MAX_STEPS` (5) | la boucle s'arrête, étape `budget` enregistrée |
| Appels d'outils | `SPORT_AGENT_MAX_TOOL_CALLS` (16) | budget global partagé par l'exécution |
| Appel identique répété | 2 × même outil + mêmes arguments | `{"ok": false, "error": "appel_repete"}` |
| Temps total | `SPORT_AGENT_TIMEOUT_SECONDS` (60) | statut `timeout`, pas de nouvelle décision |
| Actions par décision | 5 | le reste est ignoré |
| Fournisseur IA indisponible | — | statut `fallback` → **repli sur le job historique** |
| Étapes épuisées | — | statut `budget_exhausted` (terminal, accepté par le repli) |
| Réveil par événement | `AGENT_TRIGGER_COOLDOWN_MINUTES` (30 min) | déclencheur métier déjà émis récemment → `status=cooldown` |

Les erreurs sont interceptées : une exécution se termine toujours par une ligne
`terminate`, jamais par une exception remontée à l'appelant.

---

## Emplacement

| Rôle | Fichier |
|---|---|
| Drapeau, réglages | `app/core/config.py` (`SPORT_AGENT_*`) |
| Tables | `app/models/sport.py` (`SportAgentExecution`, `SportRecommendation`) |
| Migration | `alembic/versions/20260930_0032_sport_agent.py` |
| Registre d'outils | `app/services/sport_agent/tool_registry.py` |
| Outils | `app/services/sport_agent/tools/` |
| Mission / format de décision | `app/services/sport_agent/prompts.py` |
| Boucle | `app/services/sport_agent/orchestrator.py` |
| Réveils | `app/services/sport_agent/triggers.py` |
| Événements métier | `app/services/sport_agent/events.py` |
| Protocole d'outils (passerelle) | `app/services/ai_gateway/tool_protocol.py` |
| Cycle planifié | `app/services/sport_analysis_service.py` (`run_sport_analysis_cycle`) |
| Assistant IA global | `app/api/maintenance.py` (`ai_chat`) |
| Tests | `tests/test_sport_agent.py` |

---

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `SPORT_AGENT_ENABLED` | `true` | **seul interrupteur** : off = jobs historiques inchangés |
| `SPORT_AGENT_MAX_STEPS` | `5` | tours maximum de la boucle décisionnelle |
| `SPORT_AGENT_MAX_TOOL_CALLS` | `16` | budget d'outils par exécution |
| `SPORT_AGENT_TIMEOUT_SECONDS` | `60` | durée maximale d'une exécution |
| `COACH_TIP_DAILY_LIMIT` | `2` | conseils ponctuels du coach par jour (`send_coach_tip`) |

---

## Protocole d'outils (rétrocompatible)

Aucun fournisseur n'est modifié : le tool-calling est un protocole JSON posé dans le
message système, actif **uniquement** quand `tools` est fourni à `generate()`.

```jsonc
// requête du modèle
{"tool_calls": [{"name": "get_sleep", "arguments": {"day": 3}}]}
// conclusion du modèle
{"final": {"reasoning": "...", "summary": "...", "actions": [...], "follow_up": false}}
```

Sans `tools`, `generate()` se comporte exactement comme avant (tests de non-régression
`test_gateway_without_tools_keeps_legacy_contract`).

### Format de décision

```json
{
  "reasoning": "chaîne de raisonnement courte",
  "summary": "résumé lisible de la décision",
  "answer": "réponse à l'utilisateur (trigger user_request uniquement)",
  "actions": [
    {"type": "create_recommendation", "recommendation": "...", "reason": "...",
     "category": "training|recovery|other", "valid_days": 7, "objective_id": 1},
    {"type": "update_recommendation", "recommendation_id": 1,
     "status": "superseded|cancelled|expired", "reason": "..."},
    {"type": "send_notification", "title": "...", "message": "..."}
  ],
  "follow_up": false
}
```

* `"actions": []` est une décision légitime (rien à faire).
* Les **analyses** ne sont pas des actions : elles sont produites par les outils
  `generate_daily_analysis` / `generate_activity_analysis`.
* Un type inconnu est refusé (`type_inconnu:...`) et n'interrompt pas la boucle.

---

## Outils (17)

| Outil | Permission | Accès |
|---|---|---|
| `get_recent_activities`, `get_activity` | `sport.activities.read` | lecture |
| `get_active_objectives`, `get_goal_analysis` | `sport.goals.read` | lecture |
| `get_recovery`, `get_sleep`, `get_health_data` | `sport.access` | lecture |
| `get_garmin_status` | `sport.access` | lecture |
| `get_training_history`, `list_previous_analyses` | `sport.access` | lecture |
| `get_training_load` | `sport.access` | lecture |
| `get_previous_recommendations` | `sport.access` | lecture |
| `create_training_recommendation`, `update_recommendation` | `sport.access` | **écriture** |
| `send_notification` | `sport.access` | **écriture** |
| `generate_daily_analysis`, `generate_activity_analysis` | `sport.analysis.read` | **écriture** |

* Chaque appel passe par `SportToolRegistry.call()` : permission RBAC, puis handler.
  Un refus renvoie `permission_denied:<permission>` au modèle, qui continue.
* Ajouter un outil : créer la spec dans `app/services/sport_agent/tools/<module>.py`
  puis l'ajouter à `TOOL_MODULES` de `tools/__init__.py`. Il est aussitôt exposé au
  modèle et soumis au RBAC.
* `create_training_recommendation` applique trois garde-fous côté serveur (le
  modèle ne peut pas les contourner) :
  * **objectif validé** — `objective_id` fourni doit exister **et** appartenir à
    l'athlète de l'exécution (`objectif_introuvable:...` / `objectif_non_autorise:...`) ;
    sans `objective_id`, lien automatique à l'objectif actif (comportement historique) ;
  * **anti-duplication** — si une recommandation *active* (`pending`/`accepted`)
    du même athlète est identique après normalisation (NFKD sans accents,
    minuscules) ou recouvre à ≥ 80 %, **rien n'est créé** : le résultat renvoie
    `duplicate=true` et `existing_id` ;
  * **expiration déterministe** — toute recommandation `pending` dont
    `valid_until` est passé passe en `expired` au moment d'une création, et un
    **snapshot** `state_at_creation` (jour, activités sur 7 j, dernière activité,
    readiness/sommeil) est enregistré dans `result_json`.

---

## Déclencheurs

`morning`, `evening`, `activity`, `user_request`, `objective_created`,
`objective_updated`, `garmin_sync`, `recovery_change`, `training_completed`,
`training_missed`, `anomaly_detected`.

Le déclencheur décrit **quand** réveiller l'agent ; il ne contient **aucune** logique
métier. Les identifiants d'activités à analyser transitent dans le `payload`.

### Câblage des événements métier (`sport_agent/events.py`)

`emit_agent_event()` réveille immédiatement sur la session courante ;
`schedule_agent_event()` / `schedule_post_sync_events()` ouvrent une tâche de
fond avec leur propre session (pattern `_run_activity_ai_analysis`), sans rien
faire quand `SPORT_AGENT_ENABLED=false`.

| Déclencheur | Câblé ? | Émission |
|---|---|---|
| `morning` / `evening` / `activity` | **OK** | cycle planifié (`run_sport_analysis_cycle`) |
| `user_request` | **OK** | Assistant IA (`/maintenance/ai/chat`) |
| `objective_created` | **OK** | `POST /sport/goals` (tâche de fond) |
| `garmin_sync` | **OK** | `POST /sport/garmin/sync` + `sync_all_connections` → `schedule_post_sync_events` |
| `recovery_change` | **OK** | post-sync : delta readiness ≥ 15 points **ou** sommeil ≥ 90 min entre les deux derniers jours, si la donnée la plus récente date d'aujourd'hui ou d'hier |
| `anomaly_detected` | **OK** | post-sync : sommeil à 0 min, readiness < 20, sur donnée fraîche |
| `training_completed` | **OK** | post-sync : dernière activité ≤ 7 j couvrant une recommandation `training` active (marquée `training_completed_emitted_at`) |
| `training_missed` | **OK** | cycle : recommandation `training` `pending`/`accepted` dont `valid_until` est passé (marquée `missed_emitted_at`) |
| `objective_updated` | **NON** | aucune API ni service de mise à jour d'objectif n'existe dans le dépôt (uniquement `GET`/`POST /sport/goals`) : l'émettre supposerait d'inventer un endpoint. Déclencheur conservé au catalogue, jamais émis. |

**Idempotence** : cooldown `AGENT_TRIGGER_COOLDOWN_MINUTES` appliqué dans
`run_agent_trigger` pour tout déclencheur de `EVENT_TRIGGERS` (hors
`user_request`, qui doit rester immédiatement réveillable), marquage dans
`result_json` pour les événements portant sur une recommandation, et
critère de fraîcheur (J-1) pour les événements santé. Un même post-sync
n'émet jamais plus de `MAX_EVENTS_PER_SYNC` réveils.

**SportCoach legacy** : `SportCoachConversation` / `SportCoachMessage`
(`sport_coach_*`) sont les tables de l'ancien chat Coach Sport supprimé. Elles
sont conservées intactes (aucun service ni endpoint ne les utilise, seule la
migration historique les crée) ; l'agent ne les écrit jamais.

### Cycle planifié (`run_sport_analysis_cycle`)

Avec `SPORT_AGENT_ENABLED=true`, pour chaque athlète connecté à Garmin :

1. **Agent d'abord**, uniquement s'il reste du travail :
   * matin/soir : analyse du jour absente ;
   * activité : au moins une activité due non analysée ;
   * et aucun exécution pour ce déclencheur depuis
     `AGENT_TRIGGER_COOLDOWN_MINUTES` (30 min) — la boucle tourne toutes les minutes.
2. **Repli obligatoire** : le job historique n'est court-circuité que si l'agent a
   terminé (`status` ∈ {`completed`, `budget_exhausted`}) **et** que l'analyse
   attendue est confirmée en base (`ensure_ready` : `dedupe_key` du jour pour
   matin/soir, plus aucune activité due pour `activity`). Dans tous les autres
   cas (drapeau éteint, `failed`, `fallback`, `timeout`, `cooldown`, agent sans
   résultat, analyse manquante), `analyze_morning` / `analyze_evening` /
   `analyze_recent_activities` s'exécute comme par le passé.
3. **Événements** : `training_missed` est évalué après le travail planifié et
   compté dans `stats["agent_events"]`.

L'idempotence historique (`dedupe_key` par jour, une analyse par activité) est
conservée : rejouer le cycle ne duplique rien.

---

## Mémoire et réévaluation

* **Mémoire des décisions** = `SportRecommendation` (et non l'historique sportif) :
  `get_previous_recommendations` permet de ne pas recommencer la même séance et de
  remplacer (`superseded`) une recommandation devenue caduque.
* **Lien avec la page Objectifs** : chaque recommandation est reliée à l'objectif
  actif (`_active_objective_id`) quand le modèle ne fournit pas `objective_id` ;
  `SportAgentExecution.objective_id` garde la trace. Un `objective_id` fourni est
  **validé** (existence + appartenance à l'athlète) avant d'être accepté.
* **État à la création** : `result_json["state_at_creation"]` fige le contexte
  (jour, activités sur 7 j, dernière activité, readiness/sommeil) au moment de la
  recommandation ; il est exposé au modèle dans le brief (`active_recommendations`)
  pour comparer « état alors » / « état maintenant ».
* **Statuts réservés à l'utilisateur** : `accepted`, `completed`, `skipped`.
  L'agent ne peut poser que `superseded`, `cancelled`, `expired`
  (`statut_non_autorise:...` sinon).

---

## Notifications

* **Toute analyse notifie** (matin, soir, sortie) : catégorie `sport_analysis`,
  jobs historiques comme outils de l'agent (`generate_daily_analysis` /
  `generate_activity_analysis` notifient systématiquement).
* **Toute analyse est publiée** dans la conversation « Coach & Analyses » de
  l'Assistant IA (`app/services/coach_feed.py`, module `coach`) — un seul
  message par analyse, jamais de doublon.
* **Conseils ponctuels du coach** : action `send_coach_tip` (catégorie
  `coach_tip`, `data.url = "/ai"`), plafonnée à `COACH_TIP_DAILY_LIMIT` par
  jour. Au-delà, l'outil refuse (`quota_conseils_atteint:<limite>`) et le conseil
  n'est ni notifié ni publié.
* L'agent peut envoyer une alerte via `send_notification`
  (catégorie `sport_agent`, `data.url = "/sport/analyses"`).
* Sur `trigger=user_request`, `send_notification` **et** `send_coach_tip` sont
  **ignorés** (`skipped: reponse_conversationnelle`) : l'agent répond dans la
  conversation.

---

## Assistant IA global

Dans `/maintenance/ai/chat` :

* une question détectée comme sportive (`_SPORT_QUESTION_RE`) **et** une permission
  `sport.access` → réveil de l'agent en `trigger=user_request` avec la question et
  l'historique de la conversation ;
* si l'agent ne termine pas en `completed` → repli sur le coach textuel
  (`sport_ai`) puis, à défaut, sur l'assistant générique ;
* `module` devient optionnel : absent → `"sport"` si la question est sportive,
  sinon `"maintenance"` (le frontend n'envoie plus `module: 'maintenance'` en dur).

---

## Persistance

| Table | Contenu |
|---|---|
| `sport_agent_executions` | trigger, statut, `step_count`, `steps_json` (observe/decide/action/verification/…), `result_json` (décisions, actions, vérifications, appels d'outils), provider, modèle, dates |
| `sport_recommendations` | recommandation persistée, objectif lié, exécution créatrice, statut, validité |

`steps_json` ne contient que des traces compactes (identifiants, compteurs, erreurs) :
aucun prompt ni donnée personnelle complète n'y est stocké.

---

## Logs

Événements structurés, sans prompt ni secret :

```text
[SPORT-AGENT] event=started|step|decision|action|verification|tool_call|finished status=...
[SPORT-AGENT] event=tool_denied name=... permission=...
[SPORT-AGENT] event=cooldown trigger=... / event=emitted trigger=... status=...
[SPORT-ANALYSIS] Agent morning status=... → repli historique (user ...)
[SPORT-ANALYSIS] event=agent_event trigger=training_missed status=...
```

---

## Tests

```bash
.venv/bin/python -m pytest tests/test_sport_agent.py -q
.venv/bin/python -m pytest tests/test_sport_api.py tests/test_sport_analysis.py \
    tests/test_sport_auto_analysis.py tests/test_sport_garmin.py \
    tests/test_maintenance_ai_chat.py -q
```

`tests/test_sport_agent.py` (24 tests) couvre : traçabilité de l'exécution, budget
d'étapes (statut `budget_exhausted`), refus RBAC sans interruption, absence de
notification inutile, recommandation reliée à l'objectif, réévaluation
(`superseded`), statuts réservés à l'utilisateur, réponse conversationnelle sans
notification, rétrocompatibilité de la passerelle, protocole JSON, repli du cycle,
court-circuit du job historique + cooldown, routage de l'Assistant IA (module
déduit), drapeau éteint, déclencheur `activity`, réveil par événement
(`objective_created` + cooldown), `training_missed` émis une seule fois, événements
post-sync (`garmin_sync` + `training_completed`), objectif étranger refusé,
anti-duplication, analyse notifiée et publiée dans l'Assistant IA, quota
quotidien des conseils ponctuels (`send_coach_tip`), et repli du cycle quand
l'agent termine sans analyse (`ensure_ready`).

Les exécutions de test branchent la **vraie** AI Gateway sur un fournisseur scripté :
le protocole d'outils est exercé de bout en bout.
