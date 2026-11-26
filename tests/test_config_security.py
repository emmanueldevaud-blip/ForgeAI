"""Regression P0-2 : secrets et DEBUG dans docker-compose.yml.

Les tests isolent l'environnement dans un processus Python du .venv et un
repertoire de travail temporaire : aucun ``.env`` n'est cree, lu ou modifie.
Ils prouvent que SECRET_KEY est obligatoire, que DEBUG vaut False par defaut
(l'API n'expose alors ni /docs ni /redoc) et que ``docker compose config``
echoue sans SECRET_KEY mais reussit quand elle est fournie par l'environnement.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.yml"
# Valeur factice de test, jamais un secret reel.
TEST_SECRET = "test-only-not-a-real-secret-0123456789abcdef"
# URL MySQL factice : app/db/session.py construit le moteur a l'import sans
# se connecter. SQLite+StaticPool refuserait pool_size/max_overflow a cet endroit.
TEST_DATABASE_URL = "mysql://forgeai:forgeai_password@localhost:3306/forgeai"


def _clean_process_env(**overrides: str) -> dict[str, str]:
    """Environnement de processus sans secret ni configuration heritee."""
    env = os.environ.copy()
    for name in (
        "SECRET_KEY",
        "DEBUG",
        "DATABASE_URL",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_DATABASE",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
    ):
        env.pop(name, None)
        env.pop(name.lower(), None)
    env["PYTHONPATH"] = str(ROOT)
    env.update(overrides)
    return env


def _run_python(tmp_path: Path, script: str, **overrides: str) -> subprocess.CompletedProcess[str]:
    """Execute un script dans le Python courant (.venv), sans .env visible."""
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=_clean_process_env(**overrides),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_get_settings_without_secret_key_raises_validation_error(tmp_path: Path) -> None:
    script = """
from pydantic import ValidationError
from app.core.config import get_settings

try:
    get_settings()
except ValidationError as exc:
    assert "secret_key" in str(exc).lower(), str(exc)
else:
    raise AssertionError("get_settings() sans SECRET_KEY aurait du lever ValidationError")
"""
    result = _run_python(tmp_path, script, DATABASE_URL=TEST_DATABASE_URL)
    assert result.returncode == 0, result.stdout + result.stderr


def test_debug_defaults_to_false_and_hides_docs(tmp_path: Path) -> None:
    script = """
from app.core.config import get_settings
from app.main import app

settings = get_settings()
assert settings.DEBUG is False, settings.DEBUG
assert app.docs_url is None, app.docs_url
assert app.redoc_url is None, app.redoc_url
"""
    result = _run_python(
        tmp_path,
        script,
        SECRET_KEY=TEST_SECRET,
        DATABASE_URL=TEST_DATABASE_URL,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("docker") is None, reason="Docker CLI absent")
def test_compose_config_requires_secret_key_from_environment(tmp_path: Path) -> None:
    command = [
        "docker", "compose",
        "--project-directory", str(tmp_path),
        "-f", str(COMPOSE_FILE),
        "config",
    ]
    base_env = _clean_process_env()

    missing = subprocess.run(
        command,
        cwd=tmp_path,
        env=base_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert missing.returncode != 0, missing.stdout
    assert "secret_key" in (missing.stdout + missing.stderr).lower(), (
        missing.stdout + missing.stderr
    )

    ok = subprocess.run(
        command,
        cwd=tmp_path,
        env={**base_env, "SECRET_KEY": TEST_SECRET},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "your-super-secret-key-change-in-production" not in ok.stdout
    assert "mysql://forgeai:forgeai_password@mysql:3306/forgeai" in ok.stdout
    assert "DEBUG" in ok.stdout and "false" in ok.stdout
