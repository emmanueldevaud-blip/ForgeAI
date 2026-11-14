"""Service de rendu final FFmpeg pour le Studio V2."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
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
    # Couleur de fond des gaps (design.background.color) — pads vidéo.
    background_color: str = "#111111"


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
        result = subprocess.run(command, capture_output=True, check=False, timeout=3600)
        if result.returncode != 0:
            raise StudioRenderError(f"FFmpeg impossible : {result.stderr[-500:]}")
