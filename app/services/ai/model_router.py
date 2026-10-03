"""AI Model Router - routage intelligent multi-providers avec cascade de modèles.

Responsable de :
* découvrir les modèles OpenCode réellement disponibles ;
* déterminer lesquels sont gratuits ;
* appliquer l'ordre de priorité (MiMo Free → Nemotron Free → autres Free → AI Gateway) ;
* essayer le modèle suivant lorsqu'un modèle échoue ;
* basculer vers l'AI Gateway uniquement lorsque tous les modèles OpenCode utilisables ont échoué.
"""

import subprocess
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.config import Settings
from app.services.ai_gateway.errors import (
    AIQuotaExceeded,
    AIProviderUnavailable,
    AIRequestTimeout,
    AIGatewayError,
)


# ---------------------------------------------------------------------------
# Découverte dynamique des modèles OpenCode
# ---------------------------------------------------------------------------

def discover_opencode_models() -> List[Dict[str, Any]]:
    """Exécute ``opencode models`` et retourne la liste des modèles détectés.

    Chaque entrée du tableau contient au minimum :
    {
        "id": "provider/model",
        "provider": "...",
        "name": "...",
        "free": True / False / None,
        "supports_tools": True / False / None,
    }
"""
    try:
        result = subprocess.run(
            ["/home/edevaud/.opencode/bin/opencode", "models"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception:  # pragma: no cover
        return []

    output = result.stdout or ""
    models: List[Dict[str, Any]] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # Chaque ligne fait "provider/model" ou contient des métadonnées
        # On extraire ce qui ressemble à un identifiant de modèle
        # La forme est "provider/model" ou "provider/model-version"
        # On cherche les modèles connus: mimo, nemotron, et les autres
        model_id = _extract_model_id(line)
        if model_id is None:
            continue

        free = _is_model_free(model_id)
        supports_tools = _supports_tools(model_id)

        models.append(
            {
                "id": model_id,
                "provider": model_id.split("/")[0] if "/" in model_id else "opencode",
                "name": model_id,
                "free": free,
                "supports_tools": supports_tools,
            }
        )

    return models


def _extract_model_id(line: str) -> Optional[str]:
    """Extrait une ID de modèle depuis la ligne de sortie de ``opencode models``.

    La sortie de ``opencode models`` a le format ``opencode/model-name``.
    On extrait le nom de modèle après le préfixe ``opencode/``.
    """
    # La ligne commence par "opencode/" (c'est le format standard)
    # On enlève ce préfixe pour obtenir l'ID de modèle proprement dit
    if line.startswith("opencode/"):
        model_id = line[len("opencode/"):].strip()
    else:
        model_id = line.strip()

    if not model_id:
        return None

    # Filtrer les lignes qui ne ressemblent pas à des identifiants de modèle
    # (celles qui sont trop courtes ou qui contiennent des caractères spéciaux)
    if len(model_id) < 3:
        return None

    return model_id


def _is_model_free(model_id: str) -> Optional[bool]:
    """Détermine si un modèle est gratuit à partir de son ID.

    Cherche des indicateurs de coût dans l'ID du modèle.
    """
    lower = model_id.lower()
    # MiMo : les modèles mimo portant le suffixe "-free" dans OpenCode
    if "mimo" in lower:
        if "-free" in lower or lower.endswith("-v2") or lower.endswith("-free"):
            return True
        # MiMo peut aussi être détecté comme free s'il a "free" dans le nom
        if "free" in lower:
            return True
    # Nemotron : portant le suffixe "-free" dans OpenCode
    if "nemotron" in lower:
        if "-free" in lower or lower.endswith("-free"):
            return True
        if "free" in lower:
            return True
    # Autres modèles avec "free" explicite dans le nom
    if "free" in lower:
        # Vérifier que ce n'est pas juste "free" comme mot commun
        # Si le modèle contient "free" et pas d'indicateur de coût connu
        return True
    # Métadonnées non déterminables
    return None


def _supports_tools(model_id: str) -> Optional[bool]:
    """Détermine si un modèle supporte le tool calling.

    À partir des indices présents dans l'ID du modèle.
    """
    lower = model_id.lower()
    # Les modèles de coding/tool calling ont souvent "code", "tool", "function" dans le nom
    if any(kw in lower for kw in ["code", "tool", "function", "agent", "coding"]):
        return True
    # Par défaut on ne sait pas
    return None


# -------------------------------------------------------------------------
# Classification des erreurs pour le fallback
# -------------------------------------------------------------------------

FALLBACK_TRIGGERING_ERRORS = frozenset(
    {
        "AIQuotaExceeded",
        "AIProviderUnavailable",
        "AIRequestTimeout",
        # Réponse vide ou illisible (tronquée par max_tokens, contenu absent…) :
        # on tente le candidat suivant au lieu d'interrompre toute la cascade.
        "AIInvalidResponse",
    }
)


def should_fallback(error: AIGatewayError) -> bool:
    """Détermine si une erreur doit déclencher un changement de modèle.

    Returns True pour les erreurs transitoires (quota, rate limit,
    indisponibilité, réponse invalide).
    Returns False pour les erreurs applicatives ou de programmation.
    """
    if not isinstance(error, AIGatewayError):
        return False
    return type(error).__name__ in FALLBACK_TRIGGERING_ERRORS


# -------------------------------------------------------------------------
# État par modèle (cooldown, essais, etc.)
# -------------------------------------------------------------------------

class ModelState:
    """Suivi de l'état par modèle (cooldown, dernier échec, etc.)."""

    def __init__(
        self,
        model_id: str,
        provider: str,
        cooldown_seconds: float = 300.0,
        clock: Callable[[], float] = time.time,
    ):
        self.model_id = model_id
        self.provider = provider
        self.cooldown_seconds = float(cooldown_seconds)
        self._clock = clock
        self.cooldown_until: float = 0.0
        self.last_error: Optional[str] = None
        self.last_success: Optional[float] = None
        self.attempts: int = 0

    def can_attempt(self) -> bool:
        """Retourne True si le modèle peut être réessayé (hors cooldown)."""
        return self._clock() >= self.cooldown_until

    def record_failure(self, error: AIGatewayError, now: float) -> None:
        """Enregistre un échec avec classification de l'erreur."""
        self.attempts += 1
        self.last_error = type(error).__name__
        if should_fallback(error):
            # Appliquer cooldown pour les erreurs de quota / rate limit
            if isinstance(error, AIQuotaExceeded):
                # Cooldown configuré (AI_ROUTER_COOLDOWN_SECONDS, 300s par défaut)
                self.cooldown_until = now + self.cooldown_seconds
            elif isinstance(error, AIProviderUnavailable):
                self.cooldown_until = now + min(60.0, self.cooldown_seconds)
            elif isinstance(error, AIRequestTimeout):
                self.cooldown_until = now + min(30.0, self.cooldown_seconds)
        else:
            # Erreur non récupérable -> pas de cooldown, on abandonne ce modèle
            self.cooldown_until = float("inf")

    def record_success(self, now: float) -> None:
        """Enregistre un succès."""
        self.last_success = now
        self.cooldown_until = 0.0  # plus de cooldown
        self.attempts = 0


# -------------------------------------------------------------------------
# Sélection de modèle par cascade
# -------------------------------------------------------------------------


class ModelCascade:
    """Gestionnaire de cascade de sélection de modèles."""

    def __init__(self, settings: Settings, clock: Callable[[], float] | None = None):
        self.settings = settings
        self._clock: Callable[[], float] = clock or time.time
        self.opencode_models: List[Dict[str, Any]] = []
        self.model_states: Dict[str, ModelState] = {}  # "provider/model" -> ModelState
        self._provider_priority: List[str] | None = None
        self._refresh_opencode_models()

    def now(self) -> float:
        """Horloge courante de la cascade (injectable pour les tests)."""
        return self._clock()

    def _cooldown_seconds(self) -> float:
        """Cooldown configuré en base (module_configs / AI_ROUTER_COOLDOWN_SECONDS)."""
        try:
            return float(self.settings.AI_ROUTER_COOLDOWN_SECONDS or 300.0)
        except (TypeError, ValueError):  # pragma: no cover - valeur DB défensive
            return 300.0

    def _refresh_opencode_models(self) -> None:
        """Rafraîchit la liste des modèles OpenCode découverts."""
        self.opencode_models = discover_opencode_models()
        # Initialiser l'état pour chaque modèle OpenCode découvert
        for model in self.opencode_models:
            key = f"{model['provider']}/{model['id']}"
            if key not in self.model_states:
                self.model_states[key] = ModelState(
                    model["id"],
                    model["provider"],
                    cooldown_seconds=self._cooldown_seconds(),
                    clock=self._clock,
                )

    def _get_provider_order(self) -> List[str]:
        """Retourne l'ordre des providers configuré."""
        order = (self.settings.AI_PROVIDER_ORDER or "groq,gemini,openrouter").lower().split(",")
        return [p.strip() for p in order if p.strip()]

    def _model_key(self, provider: str, model: str) -> str:
        """Clé unique pour le suivi d'état d'un modèle."""
        return f"{provider}/{model}"

    def _get_model_state(self, provider: str, model: str) -> ModelState:
        """Récupère ou crée l'état d'un modèle."""
        key = self._model_key(provider, model)
        if key not in self.model_states:
            self.model_states[key] = ModelState(
                model,
                provider,
                cooldown_seconds=self._cooldown_seconds(),
                clock=self._clock,
            )
        return self.model_states[key]

    def _is_model_available(self, model_key: str) -> bool:
        """Vérifie si un modèle est disponible (pas en cooldown)."""
        state = self.model_states.get(model_key)
        if state is None:
            return False
        return state.can_attempt()

    def select_development_model_cascade(
        self,
        task_type: str = "general",
    ) -> Optional[Dict[str, str]]:
        """Sélectionne le modèle suivant selon la cascade prioritaire.

        Ordre de priorité :
        1. MiMo Free via OpenCode
        2. Nemotron Free via OpenCode
        3. Autres modèles Free disponibles via OpenCode
        4. AI Gateway providers (Groq → Gemini → OpenRouter), modèle par modèle

        Returns dict with "provider" and "model" keys, or None if no model available.
        """
        now = self.now()

        # --- Phase 1 : Essayer les modèles OpenCode Free ---
        if self.settings.AI_ROUTER_PREFER_FREE:
            free_models = self._get_free_opencode_models_priority()
            for model_key in free_models:
                if not self._is_model_available(model_key):
                    continue
                state = self.model_states[model_key]
                if state.attempts >= 1 and not state.can_attempt():
                    # En cooldown, sauter
                    continue
                # Essayer ce modèle
                provider, model = model_key.split("/", 1)
                try:
                    # Simuler un test d'appel - en pratique, la gateway appellera le provider
                    # Pour l'instant, marquer comme tenté et continuer
                    # TODO: intégrer l'appel réel via la gateway
                    state.record_success(now)
                    return {"provider": provider, "model": model}
                except Exception as exc:
                    error = exc if isinstance(exc, AIGatewayError) else AIGatewayError(str(exc))
                    if should_fallback(error):
                        state.record_failure(error, now)
                        continue  # essayer le modèle suivant
                    # Erreur non récupérable, abandonner ce modèle
                    continue

        # --- Phase 2 : Essayer les providers IA Gateway, modèle par modèle ---
        provider_order = self._get_provider_order()
        for provider_name in provider_order:
            # Récupérer le modèle configuré pour ce provider
            resolved_model = type(self)._resolve_model_for_provider(
                self.settings, provider_name, task_type
            )
            if not resolved_model:
                continue

            # Vérifier le cooldown de ce modèle spécifique
            model_key = self._model_key(provider_name, resolved_model)
            if not self._is_model_available(model_key):
                # En cooldown, essayer le prochain modèle du même provider s'il y en a un
                # ou passer au provider suivant
                continue

            state = self._get_model_state(provider_name, resolved_model)

            # Essayer ce modèle
            try:
                # En production, l'appel se fait via la gateway
                # Pour l'instant, on considère que l'essai réussit
                # et on retourne la sélection
                state.record_success(now)
                return {"provider": provider_name, "model": resolved_model}
            except AIGatewayError as exc:
                if should_fallback(exc):
                    state.record_failure(exc, now)
                    # Essayer un autre modèle du même provider si disponible
                    # (c'est la clé : ne pas rendre tout le provider indisponible)
                    # Pour l'instant, on passe au provider suivant
                    continue
                # Erreur non récupérable
                raise
                # NOTE: on ne revient pas au "for model in models" ci-dessus
                # car la gateway gère déjà le retry/fallback interne

        # --- Aucun modèle n'a réussi ---
        return None

    def build_candidates(
        self,
        task_type: str = "general",
        preferred_provider: str | None = None,
    ) -> List[Dict[str, str]]:
        """Construit l'ordre complet des candidats de la cascade.

        Ordre :
        1. modèles OpenCode Free (si AI_ROUTER_PREFER_FREE) : MiMo → Nemotron → autres ;
        2. providers AI Gateway (AI_PROVIDER_ORDER), modèle par modèle
           (modèle résolu pour le task_type puis autres modèles du catalogue) ;
        3. un provider préféré passe en tête sans changer l'ordre relatif des autres.

        Retourne des dicts {"provider": ..., "model": ...}.
        """
        candidates: List[Dict[str, str]] = []
        seen: set = set()

        def _add(provider: str, model: str) -> None:
            if not model or not provider:
                return
            key = (provider, model)
            if key in seen:
                return
            seen.add(key)
            candidates.append({"provider": provider, "model": model})

        # 1. Modèles OpenCode Free
        if self.settings.AI_ROUTER_PREFER_FREE:
            for model_key in self._get_free_opencode_models_priority():
                provider, _, model = model_key.partition("/")
                _add(provider, model)

        # 2. Providers AI Gateway, modèle par modèle
        for provider_name in self._get_provider_order():
            for model in self._provider_models(provider_name, task_type):
                _add(provider_name, model)

        # 3. Provider préféré en tête
        preferred = (preferred_provider or "").strip().lower()
        if preferred:
            preferred_first = [c for c in candidates if c["provider"] == preferred]
            if preferred_first:
                others = [c for c in candidates if c["provider"] != preferred]
                candidates = preferred_first + others

        return candidates

    def _provider_models(self, provider: str, task_type: str = "general") -> List[str]:
        """Modèles configurés pour un provider, dans l'ordre de la cascade.

        Le modèle résolu pour le task_type passe en premier, suivi des autres
        modèles du catalogue pour ce provider (permet un fallback intra-provider
        sans considérer un quota sur un modèle comme une indisponibilité du
        provider entier).
        """
        from app.services.ai_gateway.models import MODEL_CATALOG

        models: List[str] = []
        primary = type(self)._resolve_model_for_provider(self.settings, provider, task_type)
        if primary:
            models.append(primary)
        for catalog in MODEL_CATALOG.values():
            candidate = catalog.get(provider)
            if candidate and candidate not in models:
                models.append(candidate)
        return models

    @staticmethod
    def _resolve_model_for_provider(
        settings: Settings, provider: str, task_type: str = "general"
    ) -> Optional[str]:
        """Résout le modèle effectif pour un provider et un task_type."""
        from app.services.ai_gateway.models import resolve_model
        return resolve_model(settings, provider, task_type, "auto")

    def _get_free_opencode_models_priority(self) -> List[str]:
        """Retourne la liste des modèles OpenCode Free par priorité.

        Ordre : MiMo Free → Nemotron Free → autres Free

        Retourne les clés complètes 'provider/model' compatibles avec model_states.
        """
        # Séparer par priorité
        mimo_free: List[str] = []
        nemotron_free: List[str] = []
        other_free: List[str] = []

        for model in self.opencode_models:
            if model["free"] is True:
                mid = model["id"]
                key = f"{model['provider']}/{mid}"
                if "mimo" in mid.lower():
                    mimo_free.append(key)
                elif "nemotron" in mid.lower():
                    nemotron_free.append(key)
                else:
                    other_free.append(key)

        result: List[str] = []
        result.extend(mimo_free)
        result.extend(nemotron_free)
        result.extend(other_free)
        return result
