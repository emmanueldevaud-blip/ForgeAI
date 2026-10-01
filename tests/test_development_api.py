"""Tests des endpoints de l'Agent Développement et du mode Développement du chat."""

import subprocess

import pytest
from sqlalchemy import select

from app.models.maintenance import AIConversation
from app.services.ai_gateway import AIGateway, AIResponse


class FakeGateway:
    def __init__(self, text="Réponse assistant"):
        self.text = text
        self.calls: list[dict] = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return AIResponse(
            text=self.text,
            provider_used="groq",
            model_used="fake-model",
            latency=0.1,
            tokens_input=1,
            tokens_output=1,
        )


@pytest.fixture
def fake_gateway(monkeypatch):
    gateway = FakeGateway()

    def _get():
        return gateway

    monkeypatch.setattr("app.services.ai_gateway.gateway.get_ai_gateway", _get)
    return gateway


@pytest.fixture
async def ai_only_headers(db_session, auth_user, auth_headers):
    """Utilisateur n'ayant que la permission ai.use (aucun droit développement)."""
    from app.services.rbac import RBACService

    rbac = RBACService(db_session)
    role = await rbac.create_role("ai-only-test", "Assistant IA seul", is_system=False)
    perm = await rbac.get_permission_by_code("ai.use")
    await rbac.assign_permission_to_role(role.id, perm.id)
    await rbac.assign_role_to_user(auth_user.id, role.id)
    db_session.expunge_all()
    return auth_headers


def _make_git_repo(path):
    """Crée un repository Git temporaire avec une modification non committée."""
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True, capture_output=True)
    (path / "file.txt").write_text("v1")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True, timeout=10)
    (path / "file.txt").write_text("v2")


def _patch_workdir(monkeypatch, path):
    from app.core.config import get_settings

    settings = get_settings()
    settings.OPENCODE_WORK_DIR = str(path)
    monkeypatch.setattr("app.api.development.get_settings", lambda: settings)


# ============================================================
# GET /development/status
# ============================================================

async def test_status_requires_permission(client, auth_headers):
    response = await client.get("/development/status", headers=auth_headers)
    assert response.status_code == 403
    assert "development.view" in response.json()["detail"]


async def test_status_returns_git_and_task(client, admin_headers):
    response = await client.get("/development/status", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert "git" in data
    assert "task" in data


async def test_status_returns_latest_task(client, admin_headers, db_session, admin_user):
    from app.services.development_agent.service import DevelopmentService

    service = DevelopmentService(db_session, admin_user)
    task = await service.create_task(title="Ma tâche", request="Analyse le code")

    response = await client.get("/development/status", headers=admin_headers)
    assert response.status_code == 200
    payload = response.json()["task"]
    assert payload["id"] == task.id
    assert payload["title"] == "Ma tâche"
    assert payload["status"] == "pending"


# ============================================================
# POST /development/commit
# ============================================================

async def test_commit_requires_permission(client, auth_headers):
    response = await client.post(
        "/development/commit",
        json={"message": "test", "confirmed": True},
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert "development.commit" in response.json()["detail"]


async def test_commit_requires_confirmation(client, admin_headers, monkeypatch, tmp_path):
    _make_git_repo(tmp_path)
    _patch_workdir(monkeypatch, tmp_path)

    response = await client.post(
        "/development/commit",
        json={"message": "test sans confirmation", "confirmed": False},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "Confirmation" in response.json()["detail"]

    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True)
    assert len(log.stdout.strip().splitlines()) == 1


async def test_commit_with_confirmation_commits(client, admin_headers, monkeypatch, tmp_path):
    _make_git_repo(tmp_path)
    _patch_workdir(monkeypatch, tmp_path)

    response = await client.post(
        "/development/commit",
        json={"message": "feat: test du endpoint", "confirmed": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["commit_hash"]

    log = subprocess.run(["git", "log", "-1", "--pretty=%s"], cwd=tmp_path, capture_output=True, text=True)
    assert log.stdout.strip() == "feat: test du endpoint"


async def test_commit_without_changes_returns_error(client, admin_headers, monkeypatch, tmp_path):
    _make_git_repo(tmp_path)
    subprocess.run(["git", "checkout", "--", "file.txt"], cwd=tmp_path, check=True, capture_output=True)
    _patch_workdir(monkeypatch, tmp_path)

    response = await client.post(
        "/development/commit",
        json={"message": "rien à commiter", "confirmed": True},
        headers=admin_headers,
    )
    assert response.status_code == 400
    assert "Aucune modification" in response.json()["detail"]


# ============================================================
# POST /development/deploy
# ============================================================

async def test_deploy_requires_permission(client, auth_headers):
    response = await client.post(
        "/development/deploy",
        json={"confirmed": True},
        headers=auth_headers,
    )
    assert response.status_code == 403
    assert "development.deploy" in response.json()["detail"]


async def test_deploy_requires_confirmation(client, admin_headers):
    response = await client.post(
        "/development/deploy",
        json={"confirmed": False},
        headers=admin_headers,
    )
    assert response.status_code == 409
    assert "Confirmation" in response.json()["detail"]


async def test_deploy_with_confirmation_calls_tool(client, admin_headers, monkeypatch):
    from app.services.development_agent.tool_registry import DevelopmentToolRegistry, ToolSpec

    calls: list[dict] = []

    async def stub_deploy(ctx, args):
        calls.append(args)
        return {"success": True, "output": "déploiement simulé"}

    def stub_registry():
        registry = DevelopmentToolRegistry()
        registry.register(ToolSpec(
            name="deploy_production",
            description="stub",
            input_schema={"type": "object", "properties": {}},
            handler=stub_deploy,
            permission="development.deploy",
            requires_confirmation=True,
        ))
        return registry

    monkeypatch.setattr("app.api.development.build_registry", stub_registry)

    response = await client.post(
        "/development/deploy",
        json={"confirmed": True},
        headers=admin_headers,
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls == [{"confirmed": True}]


# ============================================================
# Mode Développement du chat
# ============================================================

async def test_dev_mode_triggers_development_agent(client, admin_headers, monkeypatch, fake_gateway):
    calls: list[dict] = []

    async def fake_trigger(db, user, trigger, payload=None, title=None, request=None):
        calls.append({"trigger": trigger, "request": request, "title": title})
        return {"status": "ready_for_review", "task_id": "task-42"}

    monkeypatch.setattr(
        "app.services.development_agent.service.run_development_trigger", fake_trigger
    )

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Corrige cette erreur", "module": "development"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "task-42" in data["response"]
    assert data["model"] == "development-agent"
    assert len(calls) == 1
    assert calls[0]["request"] == "Corrige cette erreur"
    assert calls[0]["trigger"] == "user_request"
    assert fake_gateway.calls == []


async def test_dev_mode_uses_development_conversation(client, admin_headers, db_session, monkeypatch, fake_gateway):
    async def fake_trigger(db, user, trigger, payload=None, title=None, request=None):
        return {"status": "ready_for_review", "task_id": "task-7"}

    monkeypatch.setattr(
        "app.services.development_agent.service.run_development_trigger", fake_trigger
    )

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Analyse ce fichier", "module": "development"},
        headers=admin_headers,
    )
    assert response.status_code == 200

    result = await db_session.execute(
        select(AIConversation).where(AIConversation.id == response.json()["conversation_id"])
    )
    conversation = result.scalar_one()
    assert conversation.module == "development"


async def test_dev_mode_without_permission_is_rejected(client, ai_only_headers, monkeypatch, fake_gateway):
    calls: list[dict] = []

    async def fake_trigger(db, user, trigger, payload=None, title=None, request=None):
        calls.append({"request": request})
        return {"status": "ready_for_review", "task_id": "task-x"}

    monkeypatch.setattr(
        "app.services.development_agent.service.run_development_trigger", fake_trigger
    )

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Ajoute cette fonctionnalité", "module": "development"},
        headers=ai_only_headers,
    )

    assert response.status_code == 403
    assert "development.execute" in response.json()["detail"]
    assert calls == []


async def test_assistant_mode_does_not_trigger_development_agent(
    client, admin_headers, monkeypatch, fake_gateway
):
    calls: list[dict] = []

    async def fake_trigger(db, user, trigger, payload=None, title=None, request=None):
        calls.append({"request": request})
        return {"status": "ready_for_review", "task_id": "task-y"}

    monkeypatch.setattr(
        "app.services.development_agent.service.run_development_trigger", fake_trigger
    )

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Corrige cette erreur"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert calls == []
    assert len(fake_gateway.calls) == 1


async def test_dev_mode_agent_disabled_returns_reason(client, admin_headers, monkeypatch, fake_gateway):
    async def fake_trigger(db, user, trigger, payload=None, title=None, request=None):
        return {"status": "disabled", "trigger": trigger}

    monkeypatch.setattr(
        "app.services.development_agent.service.run_development_trigger", fake_trigger
    )

    response = await client.post(
        "/maintenance/ai/chat",
        json={"message": "Ajoute un test", "module": "development"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["model"] == "development-agent"
    assert fake_gateway.calls == []
