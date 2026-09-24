# AI Gateway — Passerelle IA centralisée

## Architecture

```
Modules ForgeAI (Agenda, Hébergement, Sport, Maintenance, …)
        │
        ▼
  AI Gateway  (app/services/ai_gateway/)
        │
  Provider Manager (sélection, retries, quotas, fallback)
        │
 ┌──────┼────────────┐
 ▼      ▼            ▼
Groq  Gemini    OpenRouter
```

Les modules n'appellent jamais directement Groq, Gemini ni OpenRouter :
ni clé API, ni quota, ni retry, ni fallback ne sortent de la passerelle.

Aucune dépendance ajoutée : la passerelle utilise `httpx`, déjà présent.

## Emplacement

- `app/services/ai_gateway/errors.py` — erreurs normalisées
- `app/services/ai_gateway/models.py` — catalogue des modèles par `task_type`
- `app/services/ai_gateway/providers.py` — Groq / Gemini / OpenRouter
- `app/services/ai_gateway/stats.py` — statistiques et quotas en mémoire
- `app/services/ai_gateway/gateway.py` — orchestration (sélection, retries, fallback, logs)
- `app/services/ai_gateway/__init__.py` — API publique

## Variables d'environnement

| Variable | Défaut | Rôle |
|---|---|---|
| `AI_GATEWAY_ENABLED` | `true` | Active ou coupe la passerelle |
| `AI_DEFAULT_PROVIDER` | `auto` | Fournisseur par défaut (`auto` = suivre l'ordre) |
| `AI_DEFAULT_MODEL` | `auto` | Modèle par défaut (`auto` = catalogue par tâche) |
| `AI_PROVIDER_ORDER` | `groq,gemini,openrouter` | Ordre de fallback |
| `AI_TIMEOUT_SECONDS` | `30` | Timeout par appel |
| `AI_MAX_RETRIES` | `2` | Retries sur erreur temporaire (timeout, 429, 5xx, réseau) |
| `AI_RETRY_BACKOFF_SECONDS` | `1.0` | Backoff exponentiel de base |
| `GROQ_ENABLED` / `GROQ_API_KEY` / `GROQ_BASE_URL` / `GROQ_MODEL` | `true` / vide / URL officielle / vide | Provider Groq |
| `GEMINI_ENABLED` / `GEMINI_API_KEY` / `GEMINI_BASE_URL` / `GEMINI_MODEL` | idem | Provider Gemini (API compatible OpenAI) |
| `OPENROUTER_ENABLED` / `OPENROUTER_API_KEY` / `OPENROUTER_BASE_URL` / `OPENROUTER_MODEL` | idem | Provider OpenRouter |

`GROQ_MODEL` / `GEMINI_MODEL` / `OPENROUTER_MODEL` vides ⇒ catalogue
`app/services/ai_gateway/models.py` fait foi (une seule source).

Un provider sans clé ou désactivé est simplement ignoré : les autres
continuent de fonctionner.

## Utilisation

### Depuis l'interface (Administration → Assistant IA)

Route : `/administration/ai` (permission `settings_view` / `settings_update`).

La page comporte deux sous-onglets :

- **Assistant** — chat réel via la passerelle : conversations persistées
  (table `ai_conversations`, module `assistant`), choix du type de tâche
  (général / rapide / raisonnement / code), historique multi-tours,
  métadonnées du dernier appel (fournisseur, modèle, latence, tokens).
- **Paramètres** — activation de la passerelle, fournisseur et modèle par
  défaut, ordre de fallback, timeout/retries, et chaque fournisseur
  (activé, clé API, URL de base, modèle).

Endpoints associés (permission `settings_view`) :

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/admin/settings/ai/chat` | Envoie un message, renvoie la réponse + meta |
| `GET` | `/admin/settings/ai/conversations` | Liste des conversations de l'utilisateur |
| `GET` | `/admin/settings/ai/conversations/{id}` | Détail (messages) d'une conversation |
| `GET` | `/admin/settings/ai/stats` | Statistiques d'usage de la passerelle |

- Stockage paramètres : table `module_configs` (module `administration`),
  même couche que la configuration SMTP — persiste au redémarrage.
- Priorité : valeurs DB > variables d'environnement (`.env`).
- Les clés API ne sont **jamais** renvoyées au frontend : la réponse ne
  contient que `api_key_configured: true/false`. Un champ vide conserve la
  clé déjà enregistrée (stockée en base avec `is_secret=true`).
- À l'enregistrement, les valeurs sont appliquées à chaud : la passerelle
  les utilise immédiatement, sans redémarrage.

### Depuis le code

```python
from app.services.ai_gateway import ai_gateway

response = await ai_gateway.generate(
    prompt="Analyse cette demande",
    system_prompt="Tu es l'assistant ForgeAI.",
    task_type="general",     # general | fast | reasoning | coding
    model="auto",            # ou un modèle explicite
    temperature=0.2,         # optionnel
    max_tokens=500,          # optionnel
    preferred_provider=None, # optionnel : "groq" | "gemini" | "openrouter"
    history=None,            # optionnel : multi-tours
)
# history (remplace prompt) : [{"role": "user"|"assistant", "content": "..."}]
# ex. conversation en cours + nouveau message utilisateur.

response.text            # réponse texte
response.provider_used   # ex. "gemini"
response.model_used      # ex. "gemini-2.0-flash"
response.tokens_input    # tokens d'entrée si fournis par le provider
response.tokens_output   # tokens de sortie
response.latency         # secondes
response.fallback_used   # True si un provider en échec a été contourné
response.quota_status    # {"groq": "cooldown:quota_exceeded", ...}
```

Statistiques (aucun secret, aucun prompt) :

```python
stats = ai_gateway.get_stats()
```

## Fallback

Ordre par défaut : `AI_PROVIDER_ORDER=groq,gemini,openrouter`.

1. Chaque appel part du premier provider disponible (activé + clé présente +
   pas en cooldown).
2. Erreur temporaire (timeout, réseau, 429, 5xx) ⇒ retry local
   (`AI_MAX_RETRIES`, backoff exponentiel), puis passage au provider suivant.
3. `preferred_provider` est tenté en premier ; s'il échoue et que le fallback
   est possible, la requête continue avec les autres.
4. Si tous échouent : `AINoProviderAvailable`.

Cooldowns marqués automatiquement :
- 429 / quota / auth erreur : 300 s
- timeout / réseau / 5xx : 60 s

Pendant un cooldown, le provider est sauté sans appel réseau.

## Quotas et statistiques

`StatsStore` (en mémoire) suit par provider et par modèle :
requêtes, tokens entrée/sortie, erreurs, fallbacks, dernière utilisation,
statut (`ok`, `quota_exceeded`, `timeout`, `unavailable`, `auth_error`).

## Erreurs normalisées

`AINoProviderAvailable`, `AIProviderUnavailable`, `AIQuotaExceeded`,
`AIAuthenticationError`, `AIRequestTimeout`, `AIInvalidResponse`
(toutes sous `AIGatewayError`). Aucune erreur HTTP d'un provider ne remonte
telle quelle dans l'application.

## Logs

Format :

```
[AI-GATEWAY] provider=groq model=openai/gpt-oss-120b status=success latency=0.412s fallback=False
[AI-GATEWAY] provider=groq model=... status=quota_exceeded fallback=gemini
```

Ni clé API, ni prompt ne sont journalisés.

## Ajouter un provider

1. Ajouter les champs `XXX_ENABLED`, `XXX_API_KEY`, `XXX_BASE_URL`,
   `XXX_MODEL` dans `app/core/config.py`.
2. Créer une classe dans `app/services/ai_gateway/providers.py` :

```python
class MistralProvider(BaseAIProvider):
    name = "mistral"
    enabled_setting = "MISTRAL_ENABLED"
    api_key_setting = "MISTRAL_API_KEY"
    base_url_setting = "MISTRAL_BASE_URL"
```

3. L'enregistrer dans `PROVIDER_CLASSES`.
4. L'ajouter à `PROVIDER_NAMES`, à `AI_PROVIDER_ORDER` (défaut) et au
   catalogue `MODEL_CATALOG` de `models.py`.
5. Ajouter les variables dans `.env.example` et `docker-compose.yml`.

## Sécurité

- Clés uniquement côté backend (env `.env` ou `module_configs` avec
  `is_secret=true`), jamais renvoyées au frontend, jamais journalisées.
- Les conversations de l'assistant sont stockées en base
  (`ai_conversations` / `ai_messages`), isolées par utilisateur et par
  module (`assistant` pour la page Administration).
- Aucun prompt ni clé n'apparaît dans les logs `[AI-GATEWAY]`.
- Le frontend ne parle qu'au backend ForgeAI.
