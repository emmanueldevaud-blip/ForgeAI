"""Gestion explicite des captures RTSP vers HLS.

Les processus sont volontairement démarrés uniquement par une action API
autorisée. Aucun flux RTSP n'est exposé au navigateur.
"""
import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

from app.core.config import get_settings
from app.services.surveillance import decrypt_password


@dataclass
class CaptureState:
    camera_id: int
    status: str = "stopped"
    process: asyncio.subprocess.Process | None = None
    directory: Path | None = None
    error: str | None = None
    command: list[str] | None = None
    manually_stopped: bool = False
    reconnect_attempts: int = 0


class SurveillanceCaptureManager:
    def __init__(self) -> None:
        self._captures: dict[int, CaptureState] = {}
        self._lock = asyncio.Lock()

    def _directory(self, camera_id: int) -> Path:
        root = Path(get_settings().SURVEILLANCE_STORAGE_PATH).resolve()
        if camera_id < 1:
            raise ValueError("Identifiant caméra invalide")
        return root / "live" / str(camera_id)

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_.-]", "_", value)

    def _source_url(self, camera) -> str:
        if camera.protocol != "rtsp":
            raise ValueError("Seul le protocole RTSP est disponible pour la capture")
        source = camera.stream_url
        if not source:
            raise ValueError("URL RTSP manquante")
        parsed = urlparse(source)
        if parsed.scheme != "rtsp" or parsed.username or parsed.password:
            raise ValueError("URL RTSP invalide")
        username = quote(camera.username or "", safe="")
        password = quote(decrypt_password(camera.encrypted_password) or "", safe="")
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"
        if username:
            netloc = f"{username}:{password}@{netloc}"
        return urlunparse(("rtsp", netloc, parsed.path, parsed.params, parsed.query, ""))

    async def start(self, camera) -> CaptureState:
        async with self._lock:
            current = self._captures.get(camera.id)
            if current and current.process and current.process.returncode is None:
                return current
            active = sum(1 for item in self._captures.values() if item.process and item.process.returncode is None)
            if active >= get_settings().SURVEILLANCE_MAX_PROCESSES:
                raise RuntimeError("Limite de captures simultanées atteinte")
            directory = self._directory(camera.id)
            directory.mkdir(parents=True, exist_ok=True)
            for item in directory.glob("segment-*.ts"):
                item.unlink(missing_ok=True)
            playlist = directory / "index.m3u8"
            playlist.unlink(missing_ok=True)
            state = CaptureState(camera_id=camera.id, status="starting", directory=directory)
            self._captures[camera.id] = state
            args = [
                get_settings().SURVEILLANCE_FFMPEG_BIN, "-hide_banner", "-loglevel", "error",
                "-rtsp_transport", "tcp", "-i", self._source_url(camera),
                "-an", "-c:v", "copy", "-f", "hls",
                "-hls_time", str(get_settings().SURVEILLANCE_SEGMENT_SECONDS),
                "-hls_list_size", str(get_settings().SURVEILLANCE_PLAYLIST_SIZE),
                "-hls_flags", "delete_segments+append_list", str(playlist),
            ]
            state.command = args
            try:
                state.process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                state.status = "active"
                asyncio.create_task(self._watch(state))
                return state
            except (OSError, ValueError) as exc:
                state.status, state.error = "error", str(exc)
                raise RuntimeError(f"Démarrage capture impossible : {exc}") from exc

    async def _watch(self, state: CaptureState) -> None:
        while state.process:
            await state.process.wait()
            if state.manually_stopped or state.status == "stopped":
                return
            if state.reconnect_attempts >= get_settings().SURVEILLANCE_RECONNECT_ATTEMPTS:
                state.status = "error"
                state.error = f"FFmpeg s'est arrêté (code {state.process.returncode})"
                return
            delay = min(2 ** state.reconnect_attempts, get_settings().SURVEILLANCE_RECONNECT_MAX_SECONDS)
            state.reconnect_attempts += 1
            state.status = "reconnecting"
            await asyncio.sleep(delay)
            if state.manually_stopped or not state.command:
                return
            try:
                state.process = await asyncio.create_subprocess_exec(*state.command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
                state.status = "active"
            except OSError as exc:
                state.error = f"Reconnexion impossible : {type(exc).__name__}"

    async def stop(self, camera_id: int) -> CaptureState:
        async with self._lock:
            state = self._captures.get(camera_id) or CaptureState(camera_id=camera_id)
            state.manually_stopped = True
            state.reconnect_attempts = get_settings().SURVEILLANCE_RECONNECT_ATTEMPTS
            if state.process and state.process.returncode is None:
                state.status = "stopped"
                state.process.terminate()
                try:
                    await asyncio.wait_for(state.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    state.process.kill()
                    await state.process.wait()
            return state

    def state(self, camera_id: int) -> CaptureState:
        return self._captures.get(camera_id) or CaptureState(camera_id=camera_id)

    async def shutdown(self) -> None:
        for camera_id in list(self._captures):
            await self.stop(camera_id)


capture_manager = SurveillanceCaptureManager()
