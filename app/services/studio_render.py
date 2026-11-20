"""Service de rendu final FFmpeg pour le Studio V2."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.photo import Photo, PhotoJob
from app.models.user import User
from app.services.photo.jobs import enqueue_job
from app.services.photo.service import PhotoService
from app.services.photo.storage import get_photo_storage
from app.services.sport_publications import SportPublicationService


class StudioRenderError(Exception):
    pass


# Préfixes des répertoires temporaires du moteur (system temp uniquement).
_TEMP_PREFIXES = (
    "forgeai-studio-render-",
    "forgeai-studio-final-video-",
    "forgeai-studio-final-audio-",
)


def _ffmpeg_color(css: str | None) -> str:
    """Convertit une couleur CSS #rrggbb en format FFmpeg 0xrrggbb."""
    raw = (css or "#111111").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        return "0x111111"
    return f"0x{raw.lower()}"


def cleanup_orphan_studio_temps(max_age_seconds: int | None = None) -> list[str]:
    """Supprime les répertoires ``forgeai-studio-*`` orphelins du system temp.

    Sécurité :
    - uniquement sous ``tempfile.gettempdir()`` ;
    - uniquement les préfixes du moteur de rendu ;
    - âge minimal ``STUDIO_RENDER_TEMP_MAX_AGE_SECONDS`` (défaut) ;
    - **jamais** sous ``PHOTO_STORAGE_PATH`` ni ``studio_renders`` (médias,
    rendus valides). Les jobs actifs utilisent des âges bien inférieurs.
    """
    if max_age_seconds is None:
        max_age_seconds = int(get_settings().STUDIO_RENDER_TEMP_MAX_AGE_SECONDS)
    if max_age_seconds <= 0:
        return []

    temp_root = Path(tempfile.gettempdir())
    try:
        storage_root = get_photo_storage().root.resolve()
    except Exception:  # noqa: BLE001 - stockage non prêt : on n'expose rien
        storage_root = None

    removed: list[str] = []
    now = time.time()
    try:
        entries = list(temp_root.iterdir())
    except OSError:
        return []

    for path in entries:
        if not path.is_dir():
            continue
        if not path.name.startswith(_TEMP_PREFIXES):
            continue
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if storage_root is not None and (
            resolved == storage_root or storage_root in resolved.parents
        ):
            continue
        if "studio_renders" in resolved.parts:
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        if age < max_age_seconds:
            continue
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            removed.append(str(path))
    return removed


def cleanup_expired_renders() -> int:
    """Supprime les MP4 de ``studio_renders`` plus vieux que la rétention.

    ``STUDIO_RENDER_RETENTION_DAYS <= 0`` : conservation indéfinie (0 suppression).
    Ne touche jamais aux originaux, miniatures ni aux jobs en cours (fichiers
    récents protégés par l'âge).
    """
    days = int(get_settings().STUDIO_RENDER_RETENTION_DAYS)
    if days <= 0:
        return 0
    try:
        root = get_photo_storage().root / "studio_renders"
    except Exception:  # noqa: BLE001
        return 0
    if not root.is_dir():
        return 0

    cutoff = time.time() - days * 86400
    removed = 0
    try:
        candidates = list(root.rglob("*.mp4"))
    except OSError:
        return 0
    for path in candidates:
        try:
            if not path.is_file():
                continue
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
            parent = path.parent
            if parent != root and parent.is_dir():
                try:
                    next(parent.iterdir())
                except StopIteration:
                    parent.rmdir()
                except OSError:
                    pass
        except OSError:
            continue
    return removed


@dataclass(frozen=True)
class FinalClip:
    track_id: str
    clip_id: str
    start: float
    duration: float
    media_id: int | None
    source: str
    in_point: float
    out_point: float
    rotation: float
    crop: dict[str, float] | None
    mute: bool
    volume: float
    fade_in: float
    fade_out: float
    ducking_enabled: bool
    ducking_level: float


@dataclass(frozen=True)
class FinalSubtitle:
    id: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class FinalRenderPlan:
    version: int
    platform: str
    media_type: str
    width: int
    height: int
    fps: int
    final_duration: float
    video_clips: list[FinalClip]
    audio_clips: list[FinalClip]
    # Sous-titres à brûler dans la vidéo finale (J7).
    subtitles: list[FinalSubtitle] = field(default_factory=list)
    # Couleur de fond des gaps (design.background.color) — pads vidéo.
    background_color: str = "#111111"


def diaporama_timing(photo_count: int) -> tuple[float, float]:
    """(durée par photo, durée totale) pour un diaporama Reel 9:16."""
    n = max(1, int(photo_count or 1))
    if n <= 1:
        return 12.0, 12.0
    seg = max(4.0, min(60.0 / n, 8.0))
    return seg, seg * n


def _diaporama_photo_ids(design: dict[str, Any] | None, photo_id: int | None) -> list[int]:
    """Photos du diaporama : design["carousel"] (≥2) ou la photo unique."""
    raw = (design or {}).get("carousel")
    ids: list[int] = []
    if isinstance(raw, list):
        for value in raw:
            try:
                pid = int(value)
            except (TypeError, ValueError):
                continue
            if pid not in ids:
                ids.append(pid)
    if len(ids) >= 2:
        return ids
    return [int(photo_id)] if photo_id else []


class StudioRenderService:
    def __init__(self, db: AsyncSession, current_user: User) -> None:
        self.db = db
        self.current_user = current_user
        self.pub_service = SportPublicationService(db, current_user)

    async def create_render_job(self, publication_id: int) -> PhotoJob:
        publication = await self.pub_service.get_publication(publication_id)
        design = publication.design if publication else None
        if not design:
            raise ValueError("Design introuvable")

        plan = self.build_final_plan(design)
        if not plan.video_clips:
            raise ValueError("Aucune vidéo dans la timeline")
        source_id = plan.video_clips[0].media_id
        if source_id is not None and await self.db.get(Photo, source_id) is None:
            # média référencé absent : on n'expose pas de FK photo invalide
            source_id = None

        job = await enqueue_job(
            self.db,
            type="studio_render",
            photo_id=source_id,
            payload={
                "publication_id": publication_id,
                "user_id": self.current_user.id,
                "design": design,
            },
        )
        job.payload_json = {
            **(job.payload_json or {}),
            "job_id": job.id,
            "publication_id": publication_id,
            "user_id": self.current_user.id,
            "progress": {"stage": "pending", "percent": 0},
        }
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def cancel_render_job(self, job_id: str) -> PhotoJob:
        job = await self.db.get(PhotoJob, job_id)
        if job is None or job.type != "studio_render":
            raise StudioRenderError("Job de rendu introuvable")
        if job.payload_json is None or job.payload_json.get("user_id") != self.current_user.id:
            raise StudioRenderError("Accès refusé")

        if job.status in ("pending", "running"):
            job.status = "cancelled"
            job.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.error = job.error or "Annulé"
            job.payload_json = {
                **(job.payload_json or {}),
                "progress": {"stage": "cancelled", "percent": 0},
                "output_path": None,
            }
            await self.db.commit()

        return job

    async def get_render_job(self, job_id: str) -> PhotoJob:
        job = await self.db.get(PhotoJob, job_id)
        if job is None or job.type != "studio_render":
            raise StudioRenderError("Job de rendu introuvable")
        if job.payload_json is None or job.payload_json.get("user_id") != self.current_user.id:
            raise StudioRenderError("Accès refusé")
        return job

    async def get_final_render(self, job_id: str) -> Path | None:
        job = await self.get_render_job(job_id)
        if job.status != "done":
            raise StudioRenderError("Rendu final indisponible")
        output_path = job.payload_json.get("output_path") if job.payload_json else None
        if not output_path:
            raise StudioRenderError("Rendu final indisponible")
        return Path(output_path)

    async def render(
        self,
        *,
        design: dict[str, Any],
        job_id: str | None = None,
        publication_id: int | None = None,
    ) -> tuple[Path, FinalRenderPlan]:
        # Orphelins system temp d'un crash précédent (jamais les médias/rendus).
        try:
            cleanup_orphan_studio_temps()
        except Exception:  # noqa: BLE001 - le nettoyage ne doit pas bloquer
            pass

        plan = self.build_final_plan(design)
        temporary_directory = Path(tempfile.mkdtemp(prefix="forgeai-studio-render-"))
        encode_temp_dirs: list[Path] = [temporary_directory]
        final_video_path = temporary_directory / "final-video.mp4"
        final_audio_path = temporary_directory / "final-audio.m4a"
        final_path = temporary_directory / "final.mp4"

        try:
            if job_id:
                await self._update_job(
                    job_id,
                    {"progress": {"stage": "video", "percent": 30}, "output_path": None},
                )

            final_video_path = await self._encode_final_video(plan)
            encode_temp_dirs.append(final_video_path.parent)
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg is None:
                raise StudioRenderError("ffmpeg introuvable")
            final_video_path = await self._burn_subtitles(final_video_path, plan.subtitles, ffmpeg, plan.width, plan.height, plan.fps)
            if job_id:
                await self._update_job(
                    job_id,
                    {"progress": {"stage": "audio", "percent": 70}, "output_path": None},
                )

            maybe_audio = await self._encode_final_audio(plan)
            if maybe_audio is not None:
                final_audio_path = maybe_audio
                encode_temp_dirs.append(final_audio_path.parent)
            else:
                final_audio_path = None

            if job_id:
                await self._update_job(
                    job_id,
                    {"progress": {"stage": "finalize", "percent": 90}, "output_path": None},
                )

            final_path = await self._combine_final_video(
                final_video_path, final_audio_path, plan.final_duration
            )

            final_output: Path | None = None
            if publication_id and job_id:
                final_output = (
                    get_photo_storage().root
                    / "studio_renders"
                    / str(publication_id)
                    / f"{job_id}.mp4"
                )
                final_output.parent.mkdir(parents=True, exist_ok=True)
                final_output.write_bytes(final_path.read_bytes())
                final_path = final_output

            if job_id:
                await self._update_job(
                    job_id,
                    {"progress": {"stage": "done", "percent": 100}, "output_path": str(final_path)},
                )

            try:
                cleanup_expired_renders()
            except Exception:  # noqa: BLE001
                pass

            return final_path, plan
        finally:
            for temp_dir in encode_temp_dirs:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def build_final_plan(self, design: dict[str, Any]) -> FinalRenderPlan:
        if design.get("version") != 2:
            raise StudioRenderError("Le design doit être version 2")

        format_data = design.get("format") or {}
        width = int(format_data.get("width") or 1080)
        height = int(format_data.get("height") or 1350)
        timeline = design.get("timeline") or {}
        tracks = timeline.get("tracks") or []

        final_audio_clips: list[FinalClip] = []
        final_duration = 0.0
        audio_tracks = [
            t for t in tracks if t.get("type") == "audio" and not t.get("hidden")
        ]
        any_solo = any(bool(t.get("solo")) for t in audio_tracks)

        for track in audio_tracks:
            if any_solo and not track.get("solo"):
                continue
            for clip in track.get("clips") or []:
                if clip.get("type") != "audio" or not clip.get("mediaId"):
                    continue
                if clip.get("mute"):
                    continue

                in_point = float(clip.get("inPoint") or 0)
                out_point = float(clip.get("outPoint") or in_point + float(clip.get("duration") or 0))
                duration = max(0.0, out_point - in_point)
                start = float(clip.get("start") or 0)
                track_volume = float(track.get("volume") or 1)
                ducking = track.get("ducking") or {}
                ducking_level = float(1 - float(ducking.get("level") or 0)) if ducking.get("enabled") else 1.0
                gain = max(0.0, float(clip.get("volume") or 1) * track_volume * ducking_level)

                final_audio_clips.append(
                    FinalClip(
                        track_id=str(track.get("id") or ""),
                        clip_id=str(clip.get("id") or ""),
                        start=start,
                        duration=duration,
                        media_id=int(clip.get("mediaId")),
                        source=str(clip.get("source") or "forgeai"),
                        in_point=in_point,
                        out_point=out_point,
                        rotation=float(clip.get("rotation") or 0),
                        crop=clip.get("crop"),
                        mute=bool(clip.get("mute")),
                        volume=gain,
                        fade_in=float(clip.get("fadeIn") or 0),
                        fade_out=float(clip.get("fadeOut") or 0),
                        ducking_enabled=bool(ducking.get("enabled")),
                        ducking_level=ducking_level,
                    )
                )
                final_duration = max(final_duration, start + duration)

        final_video_clips: list[FinalClip] = []
        final_visual_duration = 0.0
        video_tracks = [
            t for t in tracks if t.get("type") == "video" and not t.get("hidden")
        ]
        any_video_solo = any(bool(t.get("solo")) for t in video_tracks)

        for track in video_tracks:
            if any_video_solo and not track.get("solo"):
                continue
            for clip in track.get("clips") or []:
                if clip.get("type") != "video" or not clip.get("mediaId"):
                    continue
                in_point = float(clip.get("inPoint") or 0)
                out_point = float(clip.get("outPoint") or in_point + float(clip.get("duration") or 0))
                duration = max(0.0, out_point - in_point)
                start = float(clip.get("start") or 0)
                final_video_clips.append(
                    FinalClip(
                        track_id=str(track.get("id") or ""),
                        clip_id=str(clip.get("id") or ""),
                        start=start,
                        duration=duration,
                        media_id=int(clip.get("mediaId")),
                        source=str(clip.get("source") or "forgeai"),
                        in_point=in_point,
                        out_point=out_point,
                        rotation=float(clip.get("rotation") or 0),
                        crop=clip.get("crop"),
                        mute=bool(clip.get("mute")),
                        volume=1.0,
                        fade_in=0.0,
                        fade_out=0.0,
                        ducking_enabled=False,
                        ducking_level=1.0,
                    )
                )
                final_visual_duration = max(final_visual_duration, start + duration)

        background = design.get("background") or {}
        background_color = str(background.get("color") or "#111111")

        subtitles: list[FinalSubtitle] = []
        for raw in design.get("subtitles") or []:
            if not raw or not raw.get("id") or not str(raw.get("text") or "").strip():
                continue
            sub_start = float(raw.get("start") or 0)
            sub_end = float(raw.get("end") or sub_start)
            text = str(raw.get("text") or "").strip()
            if sub_end <= sub_start:
                continue
            subtitles.append(FinalSubtitle(id=str(raw.get("id")), start=sub_start, end=sub_end, text=text))

        return FinalRenderPlan(
            version=2,
            platform=str(format_data.get("platform") or "instagram"),
            media_type=str(format_data.get("type") or "feed_45"),
            width=width,
            height=height,
            fps=int(timeline.get("fps") or 30),
            final_duration=final_duration or final_visual_duration,
            video_clips=final_video_clips,
            audio_clips=final_audio_clips,
            subtitles=subtitles,
            background_color=background_color,
        )

    async def _update_job(self, job_id: str, payload: dict[str, Any]) -> None:
        job = await self.db.get(PhotoJob, job_id)
        if job is None:
            raise StudioRenderError("Job de rendu introuvable")
        job.payload_json = {**(job.payload_json or {}), **payload}
        await self.db.commit()

    async def _resolve_media_path(self, media_id: int) -> Path:
        photo_service = PhotoService(self.db, self.current_user)
        path, _filename, _mime_type = await photo_service.resolve_file(media_id, "original")
        if not path.is_file():
            raise StudioRenderError("Fichier média final introuvable")
        return path

    @staticmethod
    def _video_vf(clip: FinalClip, plan: FinalRenderPlan) -> str:
        """Filtre vidéo : crop ratios 0..1 sur la SOURCE (iw/ih), puis scale.

        Le frontend stocke ``crop = {x,y,w,h}`` en ratios 0..1 de l'image
        source (cf. ``editorCanvas`` / ``clampCrop``). Les coordonnées FFmpeg
        du crop doivent donc être ``iw*x`` / ``ih*y``, jamais multipliées par
        le format de sortie.
        """
        chain = f"scale={plan.width}:{plan.height},setsar=1,format=yuv420p"
        if clip.crop:
            crop_width = float(clip.crop.get("w") or 1)
            crop_height = float(clip.crop.get("h") or 1)
            crop_x = float(clip.crop.get("x") or 0)
            crop_y = float(clip.crop.get("y") or 0)
            chain = (
                f"crop=iw*{crop_width}:ih*{crop_height}:iw*{crop_x}:ih*{crop_y},"
                f"scale={plan.width}:{plan.height},setsar=1,format=yuv420p"
            )
        if clip.rotation:
            chain = f"{chain},rotate={float(clip.rotation) * 3.141592653589793 / 180}"
        return chain

    def _video_segments(
        self, plan: FinalRenderPlan
    ) -> list[tuple[FinalClip | None, float]]:
        """Timeline vidéo triée : (clip, durée) ou (None, durée) pour un pad.

        Les gaps (lead-in, entre clips, trailing jusqu'à ``final_duration``)
        deviennent des segments ``None`` encodés en couleur de fond.
        """
        clips = sorted(plan.video_clips, key=lambda c: c.start)
        segments: list[tuple[FinalClip | None, float]] = []
        cursor = 0.0
        eps = 1e-6
        for clip in clips:
            if clip.start > cursor + eps:
                segments.append((None, clip.start - cursor))
            segments.append((clip, clip.duration))
            cursor = max(cursor, clip.start + clip.duration)
        if plan.final_duration > cursor + eps:
            segments.append((None, plan.final_duration - cursor))
        return segments

    async def _encode_color_pad(
        self, path: Path, plan: FinalRenderPlan, duration: float, ffmpeg: str
    ) -> None:
        color = _ffmpeg_color(plan.background_color)
        command = [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={plan.width}x{plan.height}:d={duration}:r={plan.fps}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ]
        await asyncio.to_thread(self._run_ffmpeg, command)

    async def _encode_clip_segment(
        self, path: Path, plan: FinalRenderPlan, clip: FinalClip, ffmpeg: str
    ) -> None:
        source = await self._resolve_media_path(clip.media_id or 0)
        command = [
            ffmpeg,
            "-y",
            "-ss",
            str(clip.in_point),
            "-i",
            str(source),
            "-t",
            str(clip.duration),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            self._video_vf(clip, plan),
            str(path),
        ]
        await asyncio.to_thread(self._run_ffmpeg, command)

    async def _encode_final_video(self, plan: FinalRenderPlan) -> Path:
        if not plan.video_clips:
            raise StudioRenderError("Aucune vidéo finale à rendre")

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise StudioRenderError("ffmpeg introuvable")

        temporary_directory = Path(tempfile.mkdtemp(prefix="forgeai-studio-final-video-"))
        try:
            return await self._encode_final_video_inner(plan, temporary_directory, ffmpeg)
        except Exception:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            raise

    async def _encode_final_video_inner(self, plan: FinalRenderPlan, temporary_directory: Path, ffmpeg: str) -> Path:
        segments = self._video_segments(plan)

        # Cas simple : un seul clip sans pad (pas de gap) — chemin direct.
        if len(segments) == 1 and segments[0][0] is not None:
            clip, _duration = segments[0]
            assert clip is not None
            final_video_path = temporary_directory / "final-video.mp4"
            await self._encode_clip_segment(final_video_path, plan, clip, ffmpeg)
            return final_video_path

        final_video_path = temporary_directory / "final-video-concat.mp4"
        segment_paths: list[tuple[Path, float]] = []
        for index, (clip, duration) in enumerate(segments):
            segment_path = temporary_directory / f"final-video-{index}.mp4"
            if clip is None:
                await self._encode_color_pad(segment_path, plan, duration, ffmpeg)
            else:
                await self._encode_clip_segment(segment_path, plan, clip, ffmpeg)
            segment_paths.append((segment_path, duration))

        concat_path = temporary_directory / "final-video-concat-list.txt"
        with concat_path.open("w", encoding="utf-8") as handle:
            for segment_path, segment_duration in segment_paths:
                handle.write(f"file '{segment_path}'\n")
                handle.write(f"duration {segment_duration}\n")
        command = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            str(final_video_path),
        ]
        await asyncio.to_thread(self._run_ffmpeg, command)
        return final_video_path

    async def _burn_subtitles(
        self,
        final_video_path: Path,
        subtitles: list[FinalSubtitle],
        ffmpeg: str,
        width: int,
        height: int,
        fps: int,
    ) -> Path:
        """Brule les sous-titres (SRT) dans la vidéo finale."""
        if not subtitles:
            return final_video_path
        lines: list[str] = []
        for index, sub in enumerate(subtitles, start=1):
            start_s = float(sub.start or 0)
            end_s = float(sub.end or start_s)

            def ts(value: float) -> str:
                hours = int(value // 3600)
                minutes = int((value % 3600) // 60)
                seconds = int((value % 60) * 1000)
                return f"{hours:02d}:{minutes:02d}:{seconds:03d}"

            lines.append(str(index))
            lines.append(f"{ts(start_s)} --> {ts(end_s)}")
            lines.append(str(sub.text or "").strip())
            lines.append("")
        srt_path = final_video_path.parent / "subtitles.srt"
        srt_path.write_text("\n".join(lines), encoding="utf-8")
        out_path = final_video_path.with_name("final-video-subbed.mp4")
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(final_video_path),
            "-vf",
            f"subtitles={srt_path}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
        await asyncio.to_thread(self._run_ffmpeg, command)
        return out_path

    async def _encode_final_audio(self, plan: FinalRenderPlan) -> Path | None:
        if not plan.audio_clips:
            return None

        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise StudioRenderError("ffmpeg introuvable")

        final_audio_directory = Path(tempfile.mkdtemp(prefix="forgeai-studio-final-audio-"))
        try:
            return await self._encode_final_audio_inner(plan, final_audio_directory, ffmpeg)
        except Exception:
            shutil.rmtree(final_audio_directory, ignore_errors=True)
            raise

    async def _encode_final_audio_inner(self, plan: FinalRenderPlan, final_audio_directory: Path, ffmpeg: str) -> Path | None:
        if not plan.audio_clips:
            return None
        final_audio_path = final_audio_directory / "final-audio.m4a"

        inputs: list[str] = []
        filter_parts: list[str] = []
        for index, clip in enumerate(plan.audio_clips):
            source = await self._resolve_media_path(clip.media_id or 0)
            inputs.extend(["-ss", str(clip.in_point), "-i", str(source)])
            fade_parts: list[str] = [f"volume={clip.volume}"]
            if clip.fade_in > 0:
                fade_parts.append(f"afade=t=in:st=0:d={clip.fade_in}")
            if clip.fade_out > 0:
                fade_start = max(0.0, clip.duration - clip.fade_out)
                fade_parts.append(f"afade=t=out:st={fade_start}:d={clip.fade_out}")
            delay_ms = int(round(max(0.0, clip.start) * 1000))
            if delay_ms > 0:
                fade_parts.append(f"adelay={delay_ms}|{delay_ms}")
            # Sans label final : les labels sont posés selon mono ou amix.
            filter_parts.append(
                f"[{index}:a]{','.join(fade_parts)},"
                f"aresample=44100,"
                f"aformat=channel_layouts=stereo"
            )

        if len(filter_parts) == 1:
            # apad : silence jusqu'à final_duration si l'audio est plus court
            # que la vidéo (sinon -shortest tronquerait le mix).
            filter_complex = (
                f"{filter_parts[0]},"
                f"apad=whole_dur={plan.final_duration},"
                f"atrim=0:{plan.final_duration},asetpts=PTS-STARTPTS[aout]"
            )
            map_label = "[aout]"
        else:
            labeled = [f"{fp}[a{i}]" for i, fp in enumerate(filter_parts)]
            mix_labels = "".join(f"[a{i}]" for i in range(len(filter_parts)))
            filter_complex = (
                ";".join(labeled)
                + ";"
                + mix_labels
                + f"amix=inputs={len(filter_parts)}:duration=longest:normalize=0,"
                + f"apad=whole_dur={plan.final_duration},"
                + f"atrim=0:{plan.final_duration},asetpts=PTS-STARTPTS[aout]"
            )
            map_label = "[aout]"

        command = [
            ffmpeg,
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            map_label,
            "-t",
            str(plan.final_duration),
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(final_audio_path),
        ]
        await asyncio.to_thread(self._run_ffmpeg, command)
        return final_audio_path

    async def _combine_final_video(
        self,
        final_video_path: Path,
        final_audio_path: Path | None,
        final_duration: float | None = None,
    ) -> Path:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise StudioRenderError("ffmpeg introuvable")

        final_path = final_video_path.with_name("final.mp4")
        if final_audio_path is None:
            final_path.write_bytes(final_video_path.read_bytes())
        else:
            # -t final_duration : les deux pistes sont pad/trim à la même
            # durée ; -shortest tronquerait si le concat vidéo est légèrement
            # plus court à cause des arrondis de segments.
            command = [
                ffmpeg,
                "-y",
                "-i",
                str(final_video_path),
                "-i",
                str(final_audio_path),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
            ]
            if final_duration and final_duration > 0:
                command.extend(["-t", str(final_duration)])
            else:
                command.append("-shortest")
            command.append(str(final_path))
            await asyncio.to_thread(self._run_ffmpeg, command)
        return final_path

    @staticmethod
    def _run_ffmpeg(command: list[str]) -> None:
        # Un rendu compagnon doit échouer proprement plutôt que monopoliser
        # un worker pendant une heure si FFmpeg boucle ou si une image est
        # problématique.
        try:
            result = subprocess.run(command, capture_output=True, check=False, timeout=300)
        except subprocess.TimeoutExpired as exc:
            raise StudioRenderError("FFmpeg a dépassé le délai maximal de 5 minutes") from exc
        if result.returncode != 0:
            stderr = (result.stderr or b"").decode(errors="ignore") if isinstance(result.stderr, (bytes, bytearray)) else (result.stderr or "")
            raise StudioRenderError(f"FFmpeg impossible : {stderr[-800:]}")

    # ------------------------------------------------------------------ helpers binaires / ffprobe

    @staticmethod
    def _find_binary(name: str) -> str | None:
        found = shutil.which(name)
        if found:
            return found
        # Emplacements courants hors PATH (ex. installation locale ffmpeg-8)
        candidates = [
            Path.home() / ".local" / "share" / "ffmpeg-8" / "bin" / name,
            Path("/usr/bin") / name,
            Path("/usr/local/bin") / name,
        ]
        for p in candidates:
            try:
                if p.is_file():
                    return str(p)
            except Exception:
                continue
        return None

    @classmethod
    def _probe_with_ffmpeg(cls, path: Path) -> dict[str, Any] | None:
        """Fallback quand ffprobe est indisponible/non fonctionnel : parse `ffmpeg -i` (stderr)."""
        ffmpeg = cls._find_binary("ffmpeg")
        if not ffmpeg:
            return None
        try:
            res = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30)
            out = (res.stderr or "") + (res.stdout or "")
            # Durée : Duration: HH:MM:SS.xx
            import re as _re

            dur = None
            m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", out)
            if m:
                dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            has_video = bool(_re.search(r"Stream #\d+:\d+.*Video:\s*(\w+)", out))
            has_audio = bool(_re.search(r"Stream #\d+:\d+.*Audio:\s*(\w+)", out))
            vm = _re.search(r"Stream #\d+:\d+.*Video:\s*(\w+)", out)
            am = _re.search(r"Stream #\d+:\d+.*Audio:\s*(\w+)", out)
            return {
                "available": True,
                "ok": True,
                "has_video": has_video,
                "has_audio": has_audio,
                "video_codec": (vm.group(1).lower() if vm else None),
                "audio_codec": (am.group(1).lower() if am else None),
                "duration": dur,
                "size": path.stat().st_size if path.exists() else None,
                "source": "ffmpeg",
            }
        except Exception:
            return None

    @classmethod
    def _ffprobe(cls, path: Path) -> dict[str, Any]:
        ffprobe = cls._find_binary("ffprobe")
        if not ffprobe:
            fallback = cls._probe_with_ffmpeg(path)
            return fallback or {"available": False, "reason": "ffprobe introuvable"}
        try:
            res = subprocess.run(
                [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                capture_output=True, text=True, timeout=60,
            )
            if res.returncode != 0:
                # Binaire présent mais non fonctionnel (ex. libs manquantes) -> fallback ffmpeg
                fallback = cls._probe_with_ffmpeg(path)
                if fallback:
                    return fallback
                return {"available": True, "ok": False, "error": (res.stderr or "")[-500:]}
            data = json.loads(res.stdout or "{}")
            streams = data.get("streams") or []
            v = [s for s in streams if s.get("codec_type") == "video"]
            a = [s for s in streams if s.get("codec_type") == "audio"]
            fmt = data.get("format") or {}
            return {
                "available": True,
                "ok": True,
                "has_video": bool(v),
                "has_audio": bool(a),
                "video_codec": (v[0].get("codec_name") if v else None),
                "audio_codec": (a[0].get("codec_name") if a else None),
                "duration": float(fmt.get("duration") or 0) if fmt.get("duration") else None,
                "size": int(fmt.get("size") or 0) if fmt.get("size") else None,
                "source": "ffprobe",
            }
        except Exception as exc:  # noqa: BLE001
            fallback = cls._probe_with_ffmpeg(path)
            if fallback:
                return fallback
            return {"available": True, "ok": False, "error": str(exc)}

    @staticmethod
    def _assert_companion_probe(probe: dict[str, Any], expected_duration: float) -> None:
        if not probe.get("available"):
            raise StudioRenderError(f"Vérification impossible : {probe.get('reason') or 'ffprobe indisponible'}")
        if not probe.get("ok"):
            raise StudioRenderError(f"Vérification ffprobe échouée : {probe.get('error') or 'erreur inconnue'}")
        if not probe.get("has_video"):
            raise StudioRenderError("Rendu invalide : flux vidéo manquant")
        if not probe.get("has_audio"):
            # Exigence fonctionnelle : l'audio ne doit jamais être absent silencieusement
            raise StudioRenderError("Rendu invalide : flux audio manquant (AAC requis)")
        vcodec = (probe.get("video_codec") or "").lower()
        acodec = (probe.get("audio_codec") or "").lower()
        if vcodec and vcodec not in ("h264", "avc", "avc1"):
            raise StudioRenderError(f"Codec vidéo inattendu : {vcodec} (H.264 requis)")
        if acodec and acodec not in ("aac", "mp4a", "mp4a.40.2"):
            raise StudioRenderError(f"Codec audio inattendu : {acodec} (AAC requis)")
        dur = probe.get("duration")
        if dur is not None and expected_duration > 0:
            if abs(float(dur) - float(expected_duration)) > 1.5:
                raise StudioRenderError(
                    f"Durée inattendue : {float(dur):.2f}s (attendu ~{float(expected_duration):.2f}s)"
                )

    # ---------------------------------------------------------- vidéo compagnon sportive

    async def render_sport_companion_video(
        self,
        *,
        publication_id: int,
        job_id: str | None = None,
        duration: float = 12.0,
        force: bool = False,
    ) -> tuple[Path, dict[str, Any]]:
        """Génère un MP4 9:16 (photo + overlay stats + animation + audio intégré AAC).

        Vérifie par ffprobe la présence réelle des flux vidéo (H.264) et audio (AAC).
        Échoue explicitement si l'audio est absent ou invalide (jamais de vidéo muette).
        """
        from app.models.sport import SportPublication
        from app.services.community_manager.studio import (
            CommunityManagerStudioService,
            _is_sport_publication,
            _sport_stats_from_activity,
            render_sport_overlay_image,
        )
        from app.services.community_manager.audio import resolve_track_path, normalize_audio_config

        pub = await self.db.get(SportPublication, publication_id)
        if pub is None:
            raise StudioRenderError("Publication introuvable")

        # S'assurer que l'overlay sport et l'audio sont appliqués/persistés
        if _is_sport_publication(pub):
            # Charger le contexte calendrier si besoin
            if pub.calendar_entry_id and getattr(pub, "calendar_entry", None) is None:
                from app.models.sport import EditorialCalendarEntry
                entry = await self.db.get(EditorialCalendarEntry, pub.calendar_entry_id)
                pub.calendar_entry = entry
            # _ensure_sport_defaults a besoin d'un service studio-like (current_user/db)
            # persist_overlay=False : l'overlay est composé dans les fichiers temporaires
            # du rendu, jamais enregistré dans le module photo.
            studio = CommunityManagerStudioService(self.db, self.current_user)
            pub = await studio._ensure_sport_defaults(pub, persist_overlay=False)
            await self.db.commit()
            await self.db.refresh(pub)

        if not pub.photo_id:
            raise StudioRenderError("Photo requise pour générer la vidéo musicale")

        design = pub.design if isinstance(pub.design, dict) else {}
        audio_cfg = normalize_audio_config(design.get("audio") if isinstance(design.get("audio"), dict) else {})
        ig_audio = design.get("ig_audio") if isinstance(design.get("ig_audio"), dict) else {}
        track_id = audio_cfg.get("track_id") or audio_cfg.get("track")
        # L'audio Meta est attaché côté Instagram et n'est pas un fichier local.
        # Le MP4 reçoit uniquement un silence AAC technique dans ce cas.
        meta_audio = bool(ig_audio.get("audio_id"))
        audio_path = None if meta_audio else resolve_track_path(str(track_id)) if track_id else None
        if not meta_audio and not audio_cfg.get("enabled", True):
            raise StudioRenderError("Audio désactivé sans musique Meta sélectionnée")
        if not meta_audio and (audio_path is None or not audio_path.is_file()):
            raise StudioRenderError("Fichier audio local introuvable ou indisponible")
        if not shutil.which("ffmpeg") and not self._find_binary("ffmpeg"):
            raise StudioRenderError("ffmpeg introuvable")

        # Diaporama (≥2 photos) ou photo unique, + signature d'entrée pour
        # détecter toute changement (photos, stats, titre) et re-rendre.
        photos = _diaporama_photo_ids(design, pub.photo_id)
        stats: dict[str, str] = {}
        if _is_sport_publication(pub):
            activity = await studio._get_activity_for_publication(pub)
            stats = _sport_stats_from_activity(activity)
        signature: dict[str, Any] = {
            "photos": photos,
            "stats": stats,
            "title": pub.title or "",
            "style": (design.get("editorial_engine") or {}).get("style", "performance"),
            # Style léger et déterministe : transitions visibles sans zoompan
            # (qui surcharge fortement le VPS).
            "montage_style": "trail-fade-v1",
            "audio_match": (design.get("audio") or {}).get("audio_match") or {},
            "ig_audio_id": ig_audio.get("audio_id"),
        }

        # Idempotence : rendu existant et valide (et entrée inchangée)
        if (
            not force
            and pub.companion_video_status == "ready"
            and pub.companion_video_path
            and design.get("companion_input") == signature
        ):
            existing = Path(pub.companion_video_path)
            if existing.is_file():
                try:
                    probe = self._ffprobe(existing)
                    expected = duration if len(photos) < 2 else diaporama_timing(len(photos))[1]
                    self._assert_companion_probe(probe, expected)
                    audio_cfg["embedded"] = True
                    audio_cfg["audio_status"] = "integrated"
                    design = {**design, "audio": audio_cfg, "companion_input": signature}
                    pub.design = design
                    await self.db.commit()
                    return existing, {"probe": probe, "audio": audio_cfg, "reused": True}
                except Exception:
                    pass  # régénérer si invalide

        # Marquer en cours
        pub.companion_video_status = "running"
        pub.companion_video_error = None
        if job_id:
            pub.companion_video_job_id = job_id
        audio_cfg["audio_status"] = "rendering"
        design = {**design, "audio": audio_cfg}
        pub.design = design
        await self.db.commit()

        ffmpeg = self._find_binary("ffmpeg") or "ffmpeg"
        # Qualité suffisante pour un Reel Instagram, avec un encodage nettement
        # plus rapide et un fichier plus léger à transférer vers Meta.
        width, height, fps = 1080, 1920, 30
        montage_style = str((design.get("editorial_engine") or {}).get("style") or "performance").lower()
        n_photos = len(photos)
        seg_dur = 0.0
        transition_dur = 0.0
        if n_photos >= 2:
            seg_dur, raw_target_dur = diaporama_timing(n_photos)
            transition_dur = {"cinematique": 0.8, "humour": 0.35, "dynamique": 0.25, "performance": 0.5}.get(montage_style, 0.5)
            transition_dur = min(transition_dur, max(0.1, seg_dur / 2))
            target_dur = raw_target_dur - transition_dur * (n_photos - 1)
        else:
            target_dur = max(8.0, min(float(duration or 12.0), 20.0))
        temp_dir = Path(tempfile.mkdtemp(prefix="forgeai-sport-video-"))
        try:
            photo_service = PhotoService(self.db, self.current_user)

            video_tmp = temp_dir / "video.mp4"
            audio_tmp = temp_dir / "audio.m4a"
            final_tmp = temp_dir / "final.mp4"

            # Rendu rapide d'une image fixe en 9:16. L'ancien zoompan
            # recalculait chaque frame en haute résolution et pouvait monopoliser
            # plusieurs minutes de CPU sur le VPS.
            def _segment_command(input_path: Path, seconds: float, out_path: Path) -> list[str]:
                base_vf = (
                    f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                    f"crop={width}:{height},"
                    f"format=yuv420p"
                )
                # Effets Quick Reel déterministes, appliqués dans le renderer
                # existant. Performance reste sobre ; les autres ambiances ont
                # un mouvement visuel réel et vérifiable dans le MP4.
                if montage_style == "cinematique":
                    vf = f"{base_vf},zoompan=z='min(zoom+0.0015,1.12)':d={max(1, int(seconds * fps))}:s={width}x{height}:fps={fps}"
                elif montage_style == "dynamique":
                    vf = f"{base_vf},zoompan=z='min(zoom+0.004,1.18)':d={max(1, int(seconds * fps))}:s={width}x{height}:fps={fps}"
                elif montage_style == "humour":
                    vf = f"{base_vf},hflip"
                else:
                    vf = base_vf
                return [
                    ffmpeg, "-y",
                    "-loop", "1",
                    "-t", str(seconds),
                    "-i", str(input_path),
                    "-vf", vf,
                    "-c:v", "libx264",
                    "-preset", "ultrafast",
                    "-tune", "stillimage",
                    "-crf", "26",
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(out_path),
                ]

            if n_photos >= 2:
                # Diaporama : overlay stats par photo (originaux) + segments + xfade.
                seg_paths: list[Path] = []
                for idx, pid in enumerate(photos):
                    src_path, _fn, _mt = await photo_service.resolve_file(pid, "original")
                    input_image = Path(str(src_path))
                    if stats:
                        ov_path = temp_dir / f"overlay_{idx}.jpg"
                        rendered = render_sport_overlay_image(
                            str(src_path), stats, str(ov_path), pub.title,
                            (design.get("editorial_engine") or {}).get("style"),
                        )
                        if rendered and Path(rendered).is_file():
                            input_image = Path(rendered)
                    seg_out = temp_dir / f"seg_{idx}.mp4"
                    await asyncio.to_thread(
                        self._run_ffmpeg, _segment_command(input_image, seg_dur, seg_out)
                    )
                    seg_paths.append(seg_out)
                cmd_c = [ffmpeg, "-y"]
                for segment in seg_paths:
                    cmd_c.extend(["-i", str(segment)])
                filters = []
                current = "0:v"
                cumulative_offset = seg_dur - transition_dur
                for idx in range(1, len(seg_paths)):
                    output = f"xf{idx}"
                    filters.append(
                        f"[{current}][{idx}:v]xfade=transition=fade:duration={transition_dur}:offset={cumulative_offset}[{output}]"
                    )
                    current = output
                    cumulative_offset += seg_dur - transition_dur
                cmd_c.extend([
                    "-filter_complex", ";".join(filters),
                    "-map", f"[{current}]",
                    "-an", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    str(video_tmp),
                ])
                await asyncio.to_thread(self._run_ffmpeg, cmd_c)
            else:
                # Photo unique : _ensure_sport_defaults est appelé sans persister
                # l'overlay pendant la génération vidéo. Il faut donc composer
                # ici l'image réellement encodée, comme pour un diaporama.
                photo_path, _fn, _mt = await photo_service.resolve_file(pub.photo_id, "original")
                input_image = Path(str(photo_path))
                if stats:
                    overlay_path = temp_dir / "overlay.jpg"
                    rendered = render_sport_overlay_image(
                        str(photo_path), stats, str(overlay_path), pub.title,
                        (design.get("editorial_engine") or {}).get("style"),
                    )
                    if rendered and Path(rendered).is_file():
                        input_image = Path(rendered)
                await asyncio.to_thread(
                    self._run_ffmpeg,
                    _segment_command(input_image, target_dur, video_tmp),
                )

            # Audio : normalisation simple + fades in/out, pad/trim à la durée cible, AAC
            fade_in = float(audio_cfg.get("fade_in") or 0.4)
            fade_out = float(audio_cfg.get("fade_out") or 0.8)
            vol = float(audio_cfg.get("volume") or 1.0)
            fade_out_start = max(0.0, target_dur - fade_out)
            af = (
                f"volume={vol},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={fade_out_start}:d={fade_out},"
                f"apad=whole_dur={target_dur},"
                f"atrim=0:{target_dur},"
                f"asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates=44100:channel_layouts=stereo"
            )
            cmd_a = [ffmpeg, "-y"]
            if meta_audio:
                cmd_a.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
            else:
                cmd_a.extend(["-ss", str(max(0.0, float((audio_cfg.get("audio_match") or {}).get("start_time") or 0.0))), "-i", str(audio_path)])
            cmd_a.extend(["-t", str(target_dur), "-vn", "-af", af, "-c:a", "aac", "-b:a", "128k", str(audio_tmp)])
            await asyncio.to_thread(self._run_ffmpeg, cmd_a)

            # Mux : piste audio réellement intégrée
            cmd_m = [
                ffmpeg, "-y",
                "-i", str(video_tmp),
                "-i", str(audio_tmp),
                "-c:v", "copy",
                "-c:a", "aac",
                "-t", str(target_dur),
                "-movflags", "+faststart",
                str(final_tmp),
            ]
            await asyncio.to_thread(self._run_ffmpeg, cmd_m)

            # Vérification ffprobe (obligatoire : pas de vidéo sans audio)
            probe = self._ffprobe(final_tmp)
            self._assert_companion_probe(probe, target_dur)

            # Enregistrer le rendu final (dans studio_renders/publications/<id>/)
            out_dir = get_photo_storage().root / "studio_renders" / "publications" / str(publication_id)
            out_dir.mkdir(parents=True, exist_ok=True)
            suffix = job_id or f"cmp_{int(time.time())}"
            out_path = out_dir / f"companion_{suffix}.mp4"
            out_path.write_bytes(final_tmp.read_bytes())

            audio_cfg["embedded"] = not meta_audio
            audio_cfg["audio_status"] = "meta_attached" if meta_audio else "integrated"
            design = {
                **(pub.design if isinstance(pub.design, dict) else {}),
                "audio": audio_cfg,
                "companion_input": signature,
            }
            pub.design = design
            pub.companion_video_status = "ready"
            pub.companion_video_path = str(out_path)
            pub.companion_video_error = None
            pub.companion_video_generated_at = datetime.now(timezone.utc)
            if job_id:
                pub.companion_video_job_id = job_id
            await self.db.commit()
            await self.db.refresh(pub)

            try:
                cleanup_expired_renders()
            except Exception:  # noqa: BLE001
                pass

            return out_path, {"probe": probe, "audio": audio_cfg, "reused": False}
        except Exception as exc:
            pub.companion_video_status = "failed"
            pub.companion_video_error = str(exc)
            audio_cfg["embedded"] = False
            audio_cfg["audio_status"] = "error"
            design = {**(pub.design if isinstance(pub.design, dict) else {}), "audio": audio_cfg}
            pub.design = design
            if job_id:
                pub.companion_video_job_id = job_id
            await self.db.commit()
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

