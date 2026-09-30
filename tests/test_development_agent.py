"""Tests de l'Agent Développement."""

import pytest
from sqlalchemy import select

from app.models.development import DevelopmentTask, DevelopmentAgentExecution, DevelopmentTaskStatus
from app.services.development_agent.service import DevelopmentService, run_development_trigger
from app.services.development_agent.tools import build_registry
from app.services.development_agent.opencode import OpenCodeClient
from app.core.config import get_settings


class MockOpenCodeClient(OpenCodeClient):
    """Client OpenCode factice pour les tests."""

    def __init__(self, settings, work_dir=None):
        super().__init__(settings, work_dir)
        self.calls = []

    async def run_task(self, prompt, session_id=None, continue_session=False, model=None, agent=None, timeout=300):
        self.calls.append({"prompt": prompt, "session_id": session_id})
        from app.services.development_agent.opencode import OpenCodeResult
        return OpenCodeResult(success=True, output="OK", session_id="test-session", duration_ms=100)


@pytest.fixture
def mock_opencode(monkeypatch):
    """Remplace le client OpenCode par un mock."""
    original = OpenCodeClient
    
    def mock_client(settings, work_dir=None):
        return MockOpenCodeClient(settings, work_dir)
    
    import app.services.development_agent.opencode as opencode_module
    monkeypatch.setattr(opencode_module, "OpenCodeClient", mock_client)
    monkeypatch.setattr(opencode_module, "get_opencode_client", lambda settings=None: mock_client(get_settings()))


async def test_development_service_creates_task(db_session, admin_user):
    """Création d'une tâche de développement."""
    service = DevelopmentService(db_session, admin_user)
    task = await service.create_task(
        title="Test tâche",
        request="Ajoute une fonctionnalité",
        repository=".",
    )
    assert task.id
    assert task.title == "Test tâche"
    assert task.status == "pending"
    assert task.request == "Ajoute une fonctionnalité"


async def test_development_service_lists_tasks(db_session, admin_user):
    """Liste des tâches de l'utilisateur."""
    service = DevelopmentService(db_session, admin_user)
    await service.create_task("Tâche 1", "Demande 1")
    await service.create_task("Tâche 2", "Demande 2")
    
    tasks = await service.list_tasks()
    assert len(tasks) == 2
    assert tasks[0].title == "Tâche 2"  # Plus récent en premier


async def test_development_service_get_task(db_session, admin_user):
    """Récupération d'une tâche par ID."""
    service = DevelopmentService(db_session, admin_user)
    task = await service.create_task("Test", "Demande")
    retrieved = await service.get_task(task.id)
    assert retrieved is not None
    assert retrieved.id == task.id


async def test_registry_has_tools():
    """Le registre contient tous les outils attendus."""
    registry = build_registry()
    names = registry.names()
    
    # Outils de lecture
    assert "get_repository_status" in names
    assert "read_file" in names
    assert "search_code" in names
    assert "list_files" in names
    assert "get_git_diff" in names
    
    # Outils de développement
    assert "start_development_task" in names
    assert "ask_opencode" in names
    assert "get_opencode_status" in names
    assert "get_opencode_output" in names
    assert "run_tests" in names
    assert "analyze_failure" in names
    
    # Outils Git
    assert "create_commit" in names
    assert "push_branch" in names
    assert "create_branch" in names
    
    # Outils Production
    assert "deploy_production" in names
    
    # Total
    assert len(names) == 15


async def test_opencode_client_available():
    """Le client OpenCode détecte la disponibilité."""
    settings = get_settings()
    client = OpenCodeClient(settings)
    assert client.is_available() is True


async def test_development_task_model():
    """Modèle DevelopmentTask : statuts valides."""
    statuses = [s.value for s in DevelopmentTaskStatus]
    assert "pending" in statuses
    assert "analyzing" in statuses
    assert "planning" in statuses
    assert "developing" in statuses
    assert "testing" in statuses
    assert "fixing" in statuses
    assert "ready_for_review" in statuses
    assert "committed" in statuses
    assert "pushed" in statuses
    assert "deployed" in statuses
    assert "failed" in statuses
    assert "cancelled" in statuses


async def test_run_development_trigger_disabled(db_session, admin_user, monkeypatch):
    """L'agent est désactivé par défaut."""
    monkeypatch.setattr(get_settings(), "DEVELOPMENT_AGENT_ENABLED", False)
    
    outcome = await run_development_trigger(
        db_session, admin_user, "user_request",
        request="Test", title="Test"
    )
    assert outcome["status"] == "disabled"


async def test_reading_tools_work(db_session, admin_user):
    """Les outils de lecture fonctionnent sur le repository."""
    from app.services.development_agent.tools.reading import get_repository_status, read_file, search_code, list_files, get_git_diff
    from app.services.development_agent.tool_registry import ToolContext
    from app.models.development import DevelopmentTask
    
    task = DevelopmentTask(id="test", user_id=1, title="Test", request="Test", repository=".", status="pending")
    ctx = ToolContext(db=db_session, user=admin_user, settings=get_settings(), task=task)
    
    # get_repository_status
    result = await get_repository_status(ctx, {})
    assert "branch" in result
    assert "recent_commits" in result
    
    # list_files
    result = await list_files(ctx, {"path": "app"})
    assert "tree" in result
    assert len(result["tree"]) > 0
    
    # search_code
    result = await search_code(ctx, {"pattern": "class User"})
    assert "matches" in result
    
    # get_git_diff
    result = await get_git_diff(ctx, {})
    assert "diff" in result


async def test_development_tool_requires_confirmation(db_session, admin_user):
    """create_commit et push_branch nécessitent une confirmation."""
    from app.services.development_agent.tools.git import create_commit, push_branch
    from app.services.development_agent.tool_registry import ToolContext
    from app.models.development import DevelopmentTask
    
    task = DevelopmentTask(id="test", user_id=1, title="Test", request="Test", repository=".", status="pending")
    ctx = ToolContext(db=db_session, user=admin_user, settings=get_settings(), task=task)
    
    # create_commit sans confirmed -> erreur
    result = await create_commit(ctx, {"message": "Test commit"})
    assert not result.get("success")
    assert "confirmation" in str(result.get("error", "")).lower() or result.get("requires_confirmation") is True
    
    # push_branch sans confirmed -> erreur
    result = await push_branch(ctx, {})
    assert not result.get("success")
    assert "confirmation" in str(result.get("error", "")).lower() or result.get("requires_confirmation") is True


async def test_deploy_production_requires_confirmation(db_session, admin_user):
    """deploy_production nécessite une confirmation explicite."""
    from app.services.development_agent.tools.production import deploy_production
    from app.services.development_agent.tool_registry import ToolContext
    from app.models.development import DevelopmentTask
    
    task = DevelopmentTask(id="test", user_id=1, title="Test", request="Test", repository=".", status="pending")
    ctx = ToolContext(db=db_session, user=admin_user, settings=get_settings(), task=task)
    
    result = await deploy_production(ctx, {})
    assert not result.get("success")
    assert "confirmation" in str(result.get("error", "")).lower() or result.get("requires_confirmation") is True


async def test_routing_detection():
    """Test de la détection de mots-clés de développement."""
    import re
    
    _DEVELOPMENT_QUESTION_RE = __import__("app.api.maintenance", fromlist=["_DEVELOPMENT_QUESTION_RE"])._DEVELOPMENT_QUESTION_RE
    
    # Mots-clés qui doivent déclencher
    assert _DEVELOPMENT_QUESTION_RE.search("Ajoute une fonctionnalité")
    assert _DEVELOPMENT_QUESTION_RE.search("Corrige le bug")
    assert _DEVELOPMENT_QUESTION_RE.search("Implémente une API")
    assert _DEVELOPMENT_QUESTION_RE.search("Modifie le modèle")
    assert _DEVELOPMENT_QUESTION_RE.search("Refactor le code")
    assert _DEVELOPMENT_QUESTION_RE.search("Ajoute des tests")
    assert _DEVELOPMENT_QUESTION_RE.search("Déploie en production")
    assert _DEVELOPMENT_QUESTION_RE.search("Git commit")
    assert _DEVELOPMENT_QUESTION_RE.search("Corrige l'erreur")
    
    # Mots-clés sport ne doivent pas déclencher (test isolé)
    # Note: en pratique le routage sport a la priorité si les deux matchent


async def test_registry_permissions(db_session, admin_user):
    """Les outils ont les bonnes permissions."""
    registry = build_registry()
    
    # Outils read -> permission development.read
    for name in ["get_repository_status", "read_file", "search_code", "list_files", "get_git_diff"]:
        spec = registry.get(name)
        assert spec.permission == "development.read"
        assert spec.access == "read"
    
    # Outils write -> development.execute
    for name in ["start_development_task", "ask_opencode", "run_tests", "analyze_failure", "create_branch"]:
        spec = registry.get(name)
        assert spec.permission == "development.execute"
        assert spec.access == "write"
    
    # Git tools avec confirmation
    for name in ["create_commit", "push_branch"]:
        spec = registry.get(name)
        assert spec.permission in ("development.commit", "development.push")
        assert spec.requires_confirmation is True
    
    # Production tool
    spec = registry.get("deploy_production")
    assert spec.permission == "development.deploy"
    assert spec.requires_confirmation is True