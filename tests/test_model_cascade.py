"""Tests déterministes de la cascade IA (ModelCascade + AI Gateway).

Aucun quota réel n'est consommé : les pannes sont simulées au niveau du
provider (FakeAIProvider) exactement comme la production les lèverait, et la
découverte OpenCode est figée après une seule exécution réelle du binaire.

Couverture :
* cascade OpenCode Free (MiMo → Nemotron → autres Free) ;
* fallback intra-provider (Groq, Gemini) ;
* cascade inter-provider jusqu'à OpenRouter ;
* cooldown par modèle avec horloge contrôlée ;
* classification des erreurs récupérables / non récupérables ;
* configuration DB (module_configs) ;
* parcours réel generate() → _dispatch() → ModelCascade → provider ;
* compteurs d'appels et traçabilité (aucun secret dans les logs).
"""

import logging
import re

import pytest
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.models.module import Module, ModuleConfig, ModuleStatus
from app.services.ai.model_router import discover_opencode_models, should_fallback
from app.services.ai_gateway import AIGateway, AINoProviderAvailable
from app.services.ai_gateway.config_store import apply_overrides, load_overrides
from app.services.ai_gateway.errors import (
    AIAuthenticationError,
    AIInvalidResponse,
    AIProviderUnavailable,
    AIQuotaExceeded,
    AIRequestTimeout,
)
from app.services.ai_gateway.models import MODEL_CATALOG
from app.services.development_agent.opencode import OpenCodeClient

TRACE_RE = re.compile(
    r"cascade attempt=(?P<attempt>\d+) provider=(?P<provider>\S+) model=(?P<model>\S+) "
    r"result=(?P<result>\S+) failure_reason=(?P<failure_reason>\S+) fallback=(?P<fallback>\S+)"
)


# --------------------------------------------------------------------------- #
# Outils de simulation (aucun quota réel, aucune sleeps)
# --------------------------------------------------------------------------- #


def make_settings(**values) -> Settings:
    """Settings de test isolés : pas de .env, retries à zéro, providers désactivés."""
    defaults = {
        "_env_file": None,
        "SECRET_KEY": "test-secret-key-test-secret-key-test",
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "AI_MAX_RETRIES": 0,
        "AI_RETRY_BACKOFF_SECONDS": 0,
        # Indépendant de l'environnement OS du conteneur : la cascade Free
        # doit être exercée quel que soit AI_ROUTER_PREFER_FREE de l'env.
        "AI_ROUTER_PREFER_FREE": True,
        "GROQ_ENABLED": False,
        "GROQ_API_KEY": "",
        "GEMINI_ENABLED": False,
        "GEMINI_API_KEY": "",
        "OPENROUTER_ENABLED": False,
        "OPENROUTER_API_KEY": "",
    }
    defaults.update(values)
    return Settings(**defaults)


def simulate(kind: str) -> Exception:
    """Traduit un scénario de panne en l'exception que la production lèverait."""
    if kind in ("quota_exceeded", "429", "rate_limit"):
        return AIQuotaExceeded(f"simulation {kind}")
    if kind == "timeout":
        return AIRequestTimeout(f"simulation {kind}")
    if kind in ("model_unavailable", "provider_unavailable", "connection_error"):
        return AIProviderUnavailable(f"simulation {kind}")
    if kind == "malformed_payload":
        return AIInvalidResponse(f"simulation {kind}")
    if kind in ("invalid_request", "invalid_parameter"):
        # Équivalent HTTP 400 : providers._parse_response lève
        # AIProviderUnavailable(retryable=False).
        return AIProviderUnavailable(f"simulation {kind}", retryable=False)
    if kind == "invalid_key":
        return AIAuthenticationError(f"simulation {kind}")
    raise AssertionError(f"kind de panne inconnu : {kind}")


class FakeAIProvider:
    """Provider factice branché dans la vraie AI Gateway.

    * ``script`` : {modèle: "success" | Exception} ;
    * ``default`` : comportement des modèles non scriptés ;
    * ``calls``   : compteur d'appels par modèle, dans l'ordre réel.
    """

    def __init__(
        self,
        name: str,
        script: dict | None = None,
        default: object = "success",
        text: str = "réponse",
        available: bool = True,
    ):
        self.name = name
        self.script = dict(script or {})
        self.default = default
        self.text = text
        self.available = available
        self.calls: list[str] = []

    @property
    def is_available(self) -> bool:
        return self.available

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    def count(self, model: str | None = None) -> int:
        if model is None:
            return len(self.calls)
        return self.calls.count(model)

    async def chat(self, *, model, messages, temperature, max_tokens):
        self.calls.append(model)
        outcome = self.script.get(model, self.default)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "success":
            return self.text, 10, 5
        raise AssertionError(f"outcome inconnu pour {model} : {outcome!r}")


class FakeClock:
    """Horloge contrôlée : pas de sleep() réel pour les cooldowns."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.time = start

    def __call__(self) -> float:
        return self.time

    def advance(self, seconds: float) -> None:
        self.time += seconds


def catalog_models(provider: str) -> list[str]:
    """Modèles réellement configurés pour un provider (catalogue actuel)."""
    models: list[str] = []
    for task_type in MODEL_CATALOG:
        model = MODEL_CATALOG[task_type].get(provider)
        if model and model not in models:
            models.append(model)
    return models


def free_model_ids(models: list[dict]) -> list[str]:
    """Modèles OpenCode Free dans l'ordre documenté : MiMo → Nemotron → autres."""
    free = [model["id"] for model in models if model["free"] is True]
    mimo = [mid for mid in free if "mimo" in mid.lower()]
    nemotron = [mid for mid in free if "nemotron" in mid.lower()]
    others = [mid for mid in free if mid not in mimo and mid not in nemotron]
    return mimo + nemotron + others


def build_gateway(providers: dict, *, settings: Settings | None = None, clock=None, **values) -> AIGateway:
    gateway_settings = settings or make_settings(**values)
    gateway = AIGateway(settings=gateway_settings, providers=providers)
    if clock is not None:
        from app.services.ai.model_router import ModelCascade

        gateway._cascade = ModelCascade(gateway_settings, clock=clock)
    return gateway


# --------------------------------------------------------------------------- #
# Découverte OpenCode : réelle une fois, puis figée
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def discovered_opencode_models() -> list[dict]:
    """Exécution réelle unique de `opencode models` pour tout le module."""
    return discover_opencode_models()


@pytest.fixture(autouse=True)
def opencode_discovery(monkeypatch, discovered_opencode_models):
    """Aucun test ne doit ré-exécuter le binaire : la liste est gelée."""
    snapshot = [dict(model) for model in discovered_opencode_models]
    monkeypatch.setattr(
        "app.services.ai.model_router.discover_opencode_models",
        lambda: [dict(model) for model in snapshot],
    )
    return snapshot


@pytest.fixture
def free_models(discovered_opencode_models) -> list[str]:
    models = free_model_ids(discovered_opencode_models)
    if len(models) < 3:
        pytest.skip("moins de 3 modèles OpenCode Free découverts")
    return models


# --------------------------------------------------------------------------- #
# 1-2. Cascade OpenCode Free
# --------------------------------------------------------------------------- #


async def test_opencode_free_model_fallback(free_models):
    """MiMo quota → Nemotron succès, sans solliciter aucun autre provider."""
    mimo, nemotron = free_models[0], free_models[1]
    assert "mimo" in mimo
    assert "nemotron" in nemotron

    opencode = FakeAIProvider("opencode", {mimo: simulate("quota_exceeded")})
    groq = FakeAIProvider("groq")
    gemini = FakeAIProvider("gemini")
    openrouter = FakeAIProvider("openrouter")
    gateway = build_gateway(
        {"opencode": opencode, "groq": groq, "gemini": gemini, "openrouter": openrouter}
    )

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "opencode"
    assert response.model_used == nemotron
    assert response.fallback_used is True
    assert opencode.calls == [mimo, nemotron]
    assert groq.total_calls == 0
    assert gemini.total_calls == 0
    assert openrouter.total_calls == 0


async def test_opencode_free_provider_fallback(free_models):
    """MiMo indisponible → Nemotron indisponible → autre Free : toujours OpenCode."""
    mimo, nemotron, autre_free = free_models[0], free_models[1], free_models[2]

    opencode = FakeAIProvider(
        "opencode",
        {
            mimo: simulate("model_unavailable"),
            nemotron: simulate("provider_unavailable"),
            autre_free: "success",
        },
    )
    groq = FakeAIProvider("groq")
    gemini = FakeAIProvider("gemini")
    openrouter = FakeAIProvider("openrouter")
    gateway = build_gateway(
        {"opencode": opencode, "groq": groq, "gemini": gemini, "openrouter": openrouter}
    )

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "opencode"
    assert response.model_used == autre_free
    assert opencode.calls == [mimo, nemotron, autre_free]
    # La cascade reste dans OpenCode Free avant de songer à Groq.
    assert groq.total_calls == 0
    assert gemini.total_calls == 0
    assert openrouter.total_calls == 0


# --------------------------------------------------------------------------- #
# 3-4. Fallback intra-provider (CRITIQUE)
# --------------------------------------------------------------------------- #


async def test_groq_model_fallback():
    """Un quota sur Groq A ne rend pas tout Groq indisponible : Groq B répond."""
    groq_models = catalog_models("groq")
    assert len(groq_models) >= 2, "deux modèles Groq doivent être configurés"
    model_a, model_b = groq_models[0], groq_models[1]

    groq = FakeAIProvider("groq", {model_a: simulate("quota_exceeded")})
    gemini = FakeAIProvider("gemini")
    openrouter = FakeAIProvider("openrouter")
    gateway = build_gateway({"groq": groq, "gemini": gemini, "openrouter": openrouter})

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "groq"
    assert response.model_used == model_b
    assert response.fallback_used is True
    assert groq.calls == [model_a, model_b]
    assert gemini.total_calls == 0
    assert openrouter.total_calls == 0


async def test_gemini_model_fallback():
    """Un quota sur Gemini A ne rend pas tout Gemini indisponible : Gemini B répond."""
    gemini_models = catalog_models("gemini")
    if len(gemini_models) < 2:
        pytest.skip(
            "catalogue Gemini : un seul modèle valide actuellement "
            f"({', '.join(gemini_models) or 'aucun'})"
        )
    model_a, model_b = gemini_models[0], gemini_models[1]

    groq = FakeAIProvider("groq", available=False)
    gemini = FakeAIProvider("gemini", {model_a: simulate("429")})
    openrouter = FakeAIProvider("openrouter")
    gateway = build_gateway({"groq": groq, "gemini": gemini, "openrouter": openrouter})

    response = await gateway.generate(prompt="Bonjour")

    assert response.provider_used == "gemini"
    assert response.model_used == model_b
    assert response.fallback_used is True
    assert gemini.calls == [model_a, model_b]
    assert groq.total_calls == 0
    assert openrouter.total_calls == 0


# --------------------------------------------------------------------------- #
# 5-6. Cascade inter-provider
# --------------------------------------------------------------------------- #


async def test_full_provider_cascade(free_models):
    """OpenCode → Groq → Gemini avec un ordre de tentatives strictement respecté."""
    groq_models = catalog_models("groq")
    gemini_models = catalog_models("gemini")
    assert len(groq_models) >= 2

    opencode = FakeAIProvider("opencode", default=simulate("provider_unavailable"))
    groq = FakeAIProvider(
        "groq",
        {
            groq_models[0]: simulate("quota_exceeded"),
            groq_models[1]: simulate("timeout"),
        },
        default=simulate("connection_error"),
    )
    gemini = FakeAIProvider("gemini")  # premier modèle en succès
    openrouter = FakeAIProvider("openrouter")
    gateway = build_gateway(
        {"opencode": opencode, "groq": groq, "gemini": gemini, "openrouter": openrouter}
    )

    response = await gateway.generate(prompt="Bonjour")

    expected_order = free_models + groq_models + [gemini_models[0]]
    assert opencode.calls + groq.calls + gemini.calls == expected_order
    assert response.provider_used == "gemini"
    assert response.model_used == gemini_models[0]
    assert response.fallback_used is True
    assert openrouter.total_calls == 0


async def test_openrouter_last_resort(free_models):
    """OpenCode, Groq et Gemini en échec : le dernier provider est atteint."""
    groq_models = catalog_models("groq")
    gemini_models = catalog_models("gemini")
    openrouter_models = catalog_models("openrouter")

    opencode = FakeAIProvider("opencode", default=simulate("provider_unavailable"))
    groq = FakeAIProvider("groq", default=simulate("quota_exceeded"))
    gemini = FakeAIProvider("gemini", default=simulate("timeout"))
    openrouter = FakeAIProvider("openrouter")
    gateway = build_gateway(
        {"opencode": opencode, "groq": groq, "gemini": gemini, "openrouter": openrouter}
    )

    response = await gateway.generate(prompt="Bonjour")

    expected_order = free_models + groq_models + gemini_models + [openrouter_models[0]]
    assert opencode.calls + groq.calls + gemini.calls + openrouter.calls == expected_order
    assert response.provider_used == "openrouter"
    assert response.model_used == openrouter_models[0]
    assert response.fallback_used is True


# --------------------------------------------------------------------------- #
# 7-8. Cooldown par modèle (horloge contrôlée, aucun sleep réel)
# --------------------------------------------------------------------------- #


async def test_model_cooldown():
    """Après un quota sur Groq A, la requête suivante retente Groq B (pas A)."""
    groq_models = catalog_models("groq")
    model_a, model_b = groq_models[0], groq_models[1]
    clock = FakeClock()

    groq = FakeAIProvider("groq", {model_a: simulate("quota_exceeded")})
    gateway = build_gateway(
        {"groq": groq, "gemini": FakeAIProvider("gemini"), "openrouter": FakeAIProvider("openrouter")},
        clock=clock,
    )

    first = await gateway.generate(prompt="Bonjour")
    second = await gateway.generate(prompt="Encore")

    assert first.model_used == model_b
    assert second.model_used == model_b
    assert groq.calls == [model_a, model_b, model_b]
    assert gateway._cascade._get_model_state("groq", model_a).can_attempt() is False
    assert gateway._cascade._get_model_state("groq", model_b).can_attempt() is True


async def test_cooldown_expiration():
    """Une fois le cooldown expiré (horloge avancée), Groq A redevient éligible."""
    groq_models = catalog_models("groq")
    model_a, model_b = groq_models[0], groq_models[1]
    clock = FakeClock()

    groq = FakeAIProvider("groq", {model_a: simulate("quota_exceeded")})
    settings = make_settings()
    gateway = build_gateway(
        {"groq": groq, "gemini": FakeAIProvider("gemini"), "openrouter": FakeAIProvider("openrouter")},
        settings=settings,
        clock=clock,
    )

    await gateway.generate(prompt="Bonjour")
    assert groq.calls == [model_a, model_b]

    # Immédiatement après : Groq A est en cooldown, la requête ne le retente pas.
    await gateway.generate(prompt="Encore")
    assert groq.calls == [model_a, model_b, model_b]

    # Avance de l'horloge au-delà du cooldown configuré : Groq A redevient éligible.
    clock.advance(float(settings.AI_ROUTER_COOLDOWN_SECONDS) + 1.0)
    assert gateway._cascade._get_model_state("groq", model_a).can_attempt() is True
    await gateway.generate(prompt="Encore une fois")
    assert groq.calls == [model_a, model_b, model_b, model_a, model_b]


# --------------------------------------------------------------------------- #
# 9. Classification des erreurs
# --------------------------------------------------------------------------- #


async def test_error_classification(free_models):
    # Classification actuelle de should_fallback().
    assert should_fallback(simulate("quota_exceeded")) is True
    assert should_fallback(simulate("429")) is True
    assert should_fallback(simulate("rate_limit")) is True
    assert should_fallback(simulate("timeout")) is True
    assert should_fallback(simulate("model_unavailable")) is True
    assert should_fallback(simulate("provider_unavailable")) is True
    assert should_fallback(simulate("connection_error")) is True
    # invalid_request / invalid_parameter (HTTP 400) : la classification actuelle
    # les lève comme AIProviderUnavailable => considérées comme récupérables.
    assert should_fallback(simulate("invalid_request")) is True
    assert should_fallback(simulate("invalid_parameter")) is True
    # malformed_payload (réponse vide ou illisible) : récupérable — la cascade
    # enchaîne le modèle suivant au lieu d'être interrompue.
    assert should_fallback(simulate("malformed_payload")) is True
    assert should_fallback(simulate("invalid_key")) is False
    assert should_fallback(ValueError("invalid_parameter")) is False

    # malformed_payload : le modèle suivant (Nemotron) est tenté.
    opencode_bad = FakeAIProvider("opencode", {free_models[0]: simulate("malformed_payload")})
    gateway_bad = build_gateway({"opencode": opencode_bad})
    response_bad = await gateway_bad.generate(prompt="Bonjour")
    assert opencode_bad.calls == [free_models[0], free_models[1]]
    assert response_bad.model_used == free_models[1]

    # Tous les candidats malformés : la cascade est épuisée, erreur remontée.
    opencode_all_bad = FakeAIProvider("opencode", default=simulate("malformed_payload"))
    gateway_exhausted = build_gateway(
        {
            "opencode": opencode_all_bad,
            "groq": FakeAIProvider("groq", default=simulate("malformed_payload")),
            "gemini": FakeAIProvider("gemini", default=simulate("malformed_payload")),
            "openrouter": FakeAIProvider("openrouter", default=simulate("malformed_payload")),
        }
    )
    with pytest.raises(AINoProviderAvailable):
        await gateway_exhausted.generate(prompt="Bonjour")
    assert opencode_all_bad.calls == free_models

    # Contrôle : une erreur récupérable (quota) enchaîne bien le modèle suivant.
    opencode_quota = FakeAIProvider("opencode", {free_models[0]: simulate("quota_exceeded")})
    gateway_quota = build_gateway({"opencode": opencode_quota, "groq": FakeAIProvider("groq")})
    response = await gateway_quota.generate(prompt="Bonjour")
    assert opencode_quota.calls == [free_models[0], free_models[1]]
    assert response.model_used == free_models[1]

    # invalid_request (classé récupérable aujourd'hui) : modèle suivant tenté.
    opencode_invalid = FakeAIProvider("opencode", {free_models[0]: simulate("invalid_request")})
    gateway_invalid = build_gateway({"opencode": opencode_invalid})
    response_invalid = await gateway_invalid.generate(prompt="Bonjour")
    assert opencode_invalid.calls == [free_models[0], free_models[1]]
    assert response_invalid.model_used == free_models[1]


# --------------------------------------------------------------------------- #
# 10. Configuration DB (module_configs)
# --------------------------------------------------------------------------- #


@pytest.fixture
async def administration_module(db_session):
    """Ligne module « administration » requise pour stocker les configs IA."""
    result = await db_session.execute(select(Module).where(Module.code == "administration"))
    module = result.scalar_one_or_none()
    if module is None:
        module = Module(
            code="administration",
            name="Administration",
            description="Administration système et configuration",
            icon="settings",
            order=1000,
            status=ModuleStatus.ACTIVE,
            version="1.0.0",
            route_path="/administration",
            component_path="Administration",
            is_core=True,
        )
        db_session.add(module)
        await db_session.commit()
    return module


async def set_module_configs(db, module, values: dict) -> None:
    for key, value in values.items():
        result = await db.execute(
            select(ModuleConfig).where(
                ModuleConfig.module_id == module.id, ModuleConfig.key == key
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            db.add(ModuleConfig(module_id=module.id, key=key, value=value))
        else:
            config.value = value
    await db.commit()


async def test_db_router_configuration(db_session, administration_module, free_models):
    """Le routeur lit ai_router_enabled / prefer_free / cooldown depuis la DB."""
    fields = (
        "AI_ROUTER_ENABLED",
        "AI_ROUTER_PREFER_FREE",
        "AI_ROUTER_COOLDOWN_SECONDS",
    )

    async def settings_from_db(pairs: dict) -> Settings:
        await set_module_configs(db_session, administration_module, pairs)
        overrides = await load_overrides(db_session, fields=fields)
        settings = make_settings()
        apply_overrides(settings, overrides)
        return settings

    # (a) Routage intelligent activé + préférence Free : OpenCode d'abord.
    settings_a = await settings_from_db(
        {
            "ai_router_enabled": "true",
            "ai_router_prefer_free": "true",
            "ai_router_cooldown_seconds": "42",
        }
    )
    assert settings_a.AI_ROUTER_ENABLED is True
    opencode_a = FakeAIProvider("opencode")
    gateway_a = build_gateway(
        {"opencode": opencode_a, "groq": FakeAIProvider("groq")}, settings=settings_a
    )
    response_a = await gateway_a.generate(prompt="Bonjour")
    assert response_a.provider_used == "opencode"
    assert opencode_a.total_calls == 1

    # (b) ai_router_enabled=false : la cascade est contournée.
    settings_b = await settings_from_db(
        {
            "ai_router_enabled": "false",
            "ai_router_prefer_free": "true",
            "ai_router_cooldown_seconds": "42",
        }
    )
    assert settings_b.AI_ROUTER_ENABLED is False
    opencode_b = FakeAIProvider("opencode")
    groq_b = FakeAIProvider("groq")
    gateway_b = build_gateway({"opencode": opencode_b, "groq": groq_b}, settings=settings_b)
    response_b = await gateway_b.generate(prompt="Bonjour")
    assert response_b.provider_used == "groq"
    assert opencode_b.total_calls == 0

    # (c) ai_router_prefer_free=false : cascade active mais OpenCode ignoré.
    settings_c = await settings_from_db(
        {
            "ai_router_enabled": "true",
            "ai_router_prefer_free": "false",
            "ai_router_cooldown_seconds": "42",
        }
    )
    assert settings_c.AI_ROUTER_PREFER_FREE is False
    opencode_c = FakeAIProvider("opencode")
    groq_c = FakeAIProvider("groq")
    gateway_c = build_gateway({"opencode": opencode_c, "groq": groq_c}, settings=settings_c)
    response_c = await gateway_c.generate(prompt="Bonjour")
    assert response_c.provider_used == "groq"
    assert opencode_c.total_calls == 0

    # (d) ai_router_cooldown_seconds=42 : cooldown de modèle effectivement appliqué.
    groq_models = catalog_models("groq")
    model_a, model_b = groq_models[0], groq_models[1]
    settings_d = await settings_from_db(
        {
            "ai_router_enabled": "true",
            "ai_router_prefer_free": "true",
            "ai_router_cooldown_seconds": "42",
        }
    )
    assert settings_d.AI_ROUTER_COOLDOWN_SECONDS == 42.0
    clock = FakeClock()
    groq_d = FakeAIProvider("groq", {model_a: simulate("quota_exceeded")})
    gateway_d = build_gateway({"groq": groq_d}, settings=settings_d, clock=clock)
    response_d = await gateway_d.generate(prompt="Bonjour")
    assert response_d.model_used == model_b
    state_d = gateway_d._cascade._get_model_state("groq", model_a)
    assert state_d.cooldown_until == clock() + 42.0

    # Contrôle : sans réglage DB, le cooldown par défaut (300 s) s'applique.
    clock_default = FakeClock()
    groq_default = FakeAIProvider("groq", {model_a: simulate("quota_exceeded")})
    gateway_default = build_gateway(
        {"groq": groq_default}, settings=make_settings(), clock=clock_default
    )
    await gateway_default.generate(prompt="Bonjour")
    state_default = gateway_default._cascade._get_model_state("groq", model_a)
    assert state_default.cooldown_until == clock_default() + 300.0


# --------------------------------------------------------------------------- #
# 11. Parcours réel generate() → _dispatch() → ModelCascade → provider
# --------------------------------------------------------------------------- #


async def test_dispatch_uses_model_cascade(free_models, caplog):
    groq_models = catalog_models("groq")
    opencode = FakeAIProvider("opencode", default=simulate("provider_unavailable"))
    groq = FakeAIProvider("groq", {groq_models[0]: simulate("quota_exceeded")})
    providers = {
        "opencode": opencode,
        "groq": groq,
        "gemini": FakeAIProvider("gemini"),
        "openrouter": FakeAIProvider("openrouter"),
    }
    gateway = build_gateway(providers)

    with caplog.at_level(logging.INFO):
        response = await gateway.generate(prompt="Bonjour")

    # L'ordre des tentatives suit exactement ModelCascade (Free puis Groq).
    assert opencode.calls == free_models
    assert groq.calls == [groq_models[0], groq_models[1]]
    assert response.provider_used == "groq"
    assert response.model_used == groq_models[1]
    assert any("cascade attempt=" in record.getMessage() for record in caplog.records)

    # Contrôle : AI_ROUTER_ENABLED=false => la cascade n'est pas utilisée,
    # OpenCode n'est jamais sollicité et le routage classique s'applique.
    opencode_off = FakeAIProvider("opencode", default=simulate("provider_unavailable"))
    groq_off = FakeAIProvider("groq", {groq_models[0]: simulate("quota_exceeded")})
    gateway_off = build_gateway(
        {
            "opencode": opencode_off,
            "groq": groq_off,
            "gemini": FakeAIProvider("gemini"),
        },
        AI_ROUTER_ENABLED=False,
    )
    response_off = await gateway_off.generate(prompt="Bonjour")
    assert opencode_off.total_calls == 0
    assert groq_off.calls == [groq_models[0]]
    assert response_off.provider_used == "gemini"


# --------------------------------------------------------------------------- #
# 12. Compteurs d'appels
# --------------------------------------------------------------------------- #


async def test_no_unnecessary_provider_calls(free_models):
    """Aucun provider appelé inutilement quand OpenCode Free répond au 2e essai."""
    mimo, nemotron = free_models[0], free_models[1]
    opencode = FakeAIProvider("opencode", {mimo: simulate("quota_exceeded")})
    providers = {
        "opencode": opencode,
        "groq": FakeAIProvider("groq"),
        "gemini": FakeAIProvider("gemini"),
        "openrouter": FakeAIProvider("openrouter"),
    }
    gateway = build_gateway(providers)

    response = await gateway.generate(prompt="Bonjour")
    assert response.model_used == nemotron

    counts = {name: provider.total_calls for name, provider in providers.items()}
    assert counts == {"opencode": 2, "groq": 0, "gemini": 0, "openrouter": 0}
    assert opencode.calls == [mimo, nemotron]

    stats = gateway.get_stats()
    requests = {entry["provider"]: entry["requests"] for entry in stats["providers"]}
    assert requests.get("groq", 0) == 0
    assert requests.get("gemini", 0) == 0
    assert requests.get("openrouter", 0) == 0


# --------------------------------------------------------------------------- #
# 13. Traçabilité des tentatives
# --------------------------------------------------------------------------- #


async def test_attempt_traces_and_no_secrets(free_models, caplog):
    mimo, nemotron = free_models[0], free_models[1]
    secret_groq = "gsk_super_secret_cascade"
    secret_gemini = "AIza_super_secret_cascade"

    opencode = FakeAIProvider("opencode", {mimo: simulate("quota_exceeded")})
    settings = make_settings(
        GROQ_ENABLED=True,
        GROQ_API_KEY=secret_groq,
        GEMINI_ENABLED=True,
        GEMINI_API_KEY=secret_gemini,
    )
    gateway = build_gateway(
        {"opencode": opencode, "groq": FakeAIProvider("groq"), "gemini": FakeAIProvider("gemini")},
        settings=settings,
    )

    with caplog.at_level(logging.INFO):
        response = await gateway.generate(prompt="Prompt sensible client=Acme")

    assert response.model_used == nemotron

    all_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_groq not in all_logs
    assert secret_gemini not in all_logs
    assert "Prompt sensible" not in all_logs
    assert "Bearer" not in all_logs

    attempts = [
        match.groupdict()
        for match in (TRACE_RE.search(record.getMessage()) for record in caplog.records)
        if match
    ]
    assert attempts == [
        {
            "attempt": "1",
            "provider": "opencode",
            "model": mimo,
            "result": "failure",
            "failure_reason": "quota_exceeded",
            "fallback": f"opencode/{nemotron}",
        },
        {
            "attempt": "2",
            "provider": "opencode",
            "model": nemotron,
            "result": "success",
            "failure_reason": "-",
            "fallback": "none",
        },
    ]


# --------------------------------------------------------------------------- #
# 14. Test réel minimal (aucun quota provoqué)
# --------------------------------------------------------------------------- #


async def test_real_first_opencode_free_model(tmp_path):
    """Un seul test réel : premier modèle OpenCode Free, sans quota/429/timeout."""
    discovered = discover_opencode_models()  # réel, non mocké
    free = free_model_ids(discovered)
    if not free:
        pytest.skip("aucun modèle OpenCode Free découvert")

    client = OpenCodeClient(get_settings(), work_dir=str(tmp_path))
    if not client.is_available():
        pytest.skip("binaire OpenCode indisponible")

    result = await client.run_task(
        "Réponds uniquement par : OK",
        model=f"opencode/{free[0]}",
        timeout=120,
    )

    assert result.success, result.error
    assert "OK" in result.output


