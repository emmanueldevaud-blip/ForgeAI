"""Client OpenCode pour l'Agent Développement."""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings


@dataclass
class OpenCodeResult:
    """Résultat d'une exécution OpenCode."""

    success: bool
    output: str
    error: str | None = None
    session_id: str | None = None
    duration_ms: int = 0
    files_modified: list[str] = None
    exit_code: int = 0

    def __post_init__(self):
        if self.files_modified is None:
            self.files_modified = []


class OpenCodeClient:
    """Client pour piloter OpenCode via CLI ou ACP."""

    def __init__(self, settings: Settings, work_dir: str | None = None):
        self.settings = settings
        self.work_dir = work_dir or settings.OPENCODE_WORK_DIR or "."
        self.opencode_bin = getattr(settings, "OPENCODE_BIN", None) or shutil.which("opencode") or "/home/edevaud/.opencode/bin/opencode"
        self._server_process: subprocess.Popen | None = None
        self._server_port: int | None = None

    async def run_task(
        self,
        prompt: str,
        session_id: str | None = None,
        continue_session: bool = False,
        model: str | None = None,
        agent: str | None = None,
        timeout: int = 300,
    ) -> OpenCodeResult:
        """Exécute une tâche OpenCode en mode run (non-interactif)."""
        started = time.monotonic()
        cmd = [self.opencode_bin, "run"]

        if session_id:
            cmd.extend(["--session", session_id])
        if continue_session:
            cmd.append("--continue")
        if model:
            cmd.extend(["--model", model])
        if agent:
            cmd.extend(["--agent", agent])

        cmd.append(prompt)

        env = os.environ.copy()
        env["OPENCODE_WORK_DIR"] = self.work_dir

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=self.work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                ),
                timeout=timeout,
            )
            stdout, stderr = await proc.communicate()
            duration_ms = int((time.monotonic() - started) * 1000)

            output = stdout.decode("utf-8", errors="replace")
            error = stderr.decode("utf-8", errors="replace")

            # Tenter d'extraire un session_id de la sortie
            extracted_session = self._extract_session_id(output)

            return OpenCodeResult(
                success=proc.returncode == 0,
                output=output,
                error=error if proc.returncode != 0 else None,
                session_id=extracted_session or session_id,
                duration_ms=duration_ms,
                exit_code=proc.returncode,
            )
        except asyncio.TimeoutError:
            return OpenCodeResult(
                success=False,
                output="",
                error=f"Timeout après {timeout}s",
                duration_ms=int((time.monotonic() - started) * 1000),
                exit_code=-1,
            )
        except Exception as exc:
            return OpenCodeResult(
                success=False,
                output="",
                error=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - started) * 1000),
                exit_code=-1,
            )

    async def start_server(self, port: int = 0, hostname: str = "127.0.0.1") -> int:
        """Démarre le serveur ACP OpenCode en arrière-plan."""
        if self._server_process and self._server_process.poll() is None:
            return self._server_port or 0

        cmd = [self.opencode_bin, "serve"]
        if port:
            cmd.extend(["--port", str(port)])
        cmd.extend(["--hostname", hostname])

        env = os.environ.copy()
        env["OPENCODE_WORK_DIR"] = self.work_dir

        self._server_process = subprocess.Popen(
            cmd,
            cwd=self.work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Attendre que le serveur soit prêt (port attribué si port=0)
        await asyncio.sleep(2)
        if self._server_process.poll() is not None:
            _, stderr = self._server_process.communicate()
            raise RuntimeError(f"Serveur OpenCode échoué: {stderr.decode()}")

        # Pour port=0, on ne peut pas récupérer le port facilement sans parser les logs
        # On utilise le port demandé ou 0
        self._server_port = port
        return self._server_port

    async def stop_server(self) -> None:
        """Arrête le serveur ACP."""
        if self._server_process and self._server_process.poll() is None:
            self._server_process.terminate()
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, self._server_process.wait),
                    timeout=5,
                )
            except asyncio.TimeoutError:
                self._server_process.kill()
                await asyncio.get_event_loop().run_in_executor(None, self._server_process.wait)
        self._server_process = None
        self._server_port = None

    def _extract_session_id(self, output: str) -> str | None:
        """Tente d'extraire un session_id de la sortie OpenCode."""
        import re
        # Format possible: "session: abc123" ou JSON avec session_id
        for line in output.splitlines():
            if "session" in line.lower() and ("id" in line.lower() or ":" in line):
                parts = line.split(":")
                if len(parts) >= 2:
                    candidate = parts[-1].strip()
                    if candidate and len(candidate) > 5:
                        return candidate
        return None

    async def get_status(self, session_id: str) -> dict[str, Any]:
        """Récupère le statut d'une session via export."""
        cmd = [self.opencode_bin, "export", session_id]
        env = os.environ.copy()
        env["OPENCODE_WORK_DIR"] = self.work_dir

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                return json.loads(stdout.decode())
            return {"error": stderr.decode()}
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}

    def is_available(self) -> bool:
        """Vérifie si OpenCode est disponible."""
        return shutil.which(self.opencode_bin) is not None or Path(self.opencode_bin).exists()


def get_opencode_client(settings: Settings | None = None) -> OpenCodeClient:
    """Factory pour le client OpenCode."""
    from app.core.config import get_settings
    if settings is None:
        settings = get_settings()
    return OpenCodeClient(settings)