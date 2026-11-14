"""Tests ciblés du plan de rendu final Studio V2 (sans FFmpeg)."""

import time
from pathlib import Path

import pytest

from app.services.studio_render import (
    FinalClip,
    FinalRenderPlan,
    StudioRenderError,
    StudioRenderService,
    _ffmpeg_color,
    cleanup_expired_renders,
    cleanup_orphan_studio_temps,
)


def _service() -> StudioRenderService:
    return StudioRenderService(db=None, current_user=None)


def _clip(
    *,
    id: str,
    type_: str,
    media_id: int,
    start: float = 0,
    duration: float = 2,
    volume: float = 1,
    mute: bool = False,
    fade_in: float = 0,
    fade_out: float = 0,
) -> dict:
    return {
        "id": id,
        "type": type_,
        "mediaId": media_id,
        "start": start,
        "inPoint": 0,
        "outPoint": duration,
        "duration": duration,
        "volume": volume,
        "mute": mute,
        "fadeIn": fade_in,
        "fadeOut": fade_out,
    }


def _track(
    *,
    id: str,
    type_: str,
    clips: list[dict],
    volume: float = 1,
    solo: bool = False,
    hidden: bool = False,
    ducking: dict | None = None,
) -> dict:
    return {
        "id": id,
        "type": type_,
        "volume": volume,
        "solo": solo,
        "hidden": hidden,
        "ducking": ducking or {"enabled": False, "level": 0},
        "clips": clips,
    }


class TestBuildFinalPlan:
    def test_requires_version_2(self):
        with pytest.raises(StudioRenderError):
            _service().build_final_plan({"version": 1})

    def test_multi_video_durations_and_audio_mix(self):
        design = {
            "version": 2,
            "format": {"platform": "instagram", "type": "feed_45", "width": 720, "height": 1280},
            "timeline": {
                "fps": 30,
                "tracks": [
                    _track(
                        id="v1",
                        type_="video",
                        clips=[
                            _clip(id="v1a", type_="video", media_id=10, duration=3),
                            _clip(id="v1b", type_="video", media_id=11, start=3, duration=4),
                        ],
                    ),
                    _track(
                        id="a1",
                        type_="audio",
                        clips=[
                            _clip(id="a1a", type_="audio", media_id=20, duration=6, volume=0.8, fade_in=0.5, fade_out=0.5)
                        ],
                    ),
                    _track(
                        id="a2",
                        type_="audio",
                        clips=[
                            _clip(id="a2a", type_="audio", media_id=21, duration=6, volume=0.5),
                            _clip(id="a2m", type_="audio", media_id=21, start=6, duration=2, mute=True),
                        ],
                        ducking={"enabled": True, "level": 0.5},
                    ),
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert plan.width == 720 and plan.height == 1280
        assert plan.fps == 30
        assert [c.duration for c in plan.video_clips] == [3, 4]
        assert plan.final_duration == 6
        assert len(plan.audio_clips) == 2
        # ducking statique : gain = volume_clip * volume_track * (1 - level)
        music = plan.audio_clips[1]
        assert music.volume == pytest.approx(0.5 * 1.0 * 0.5)
        voice = plan.audio_clips[0]
        assert voice.volume == pytest.approx(0.8)
        assert voice.fade_in == 0.5 and voice.fade_out == 0.5
        # clip muet exclu du mix
        assert all(c.clip_id != "a2m" for c in plan.audio_clips)

    def test_solo_excludes_non_solo_audio_tracks(self):
        design = {
            "version": 2,
            "format": {"width": 1080, "height": 1350},
            "timeline": {
                "fps": 30,
                "tracks": [
                    _track(
                        id="voice",
                        type_="audio",
                        clips=[_clip(id="c1", type_="audio", media_id=1)],
                    ),
                    _track(
                        id="music",
                        type_="audio",
                        solo=True,
                        clips=[_clip(id="c2", type_="audio", media_id=2)],
                    ),
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert [c.track_id for c in plan.audio_clips] == ["music"]

    def test_hidden_tracks_ignored(self):
        design = {
            "version": 2,
            "format": {"width": 1080, "height": 1350},
            "timeline": {
                "fps": 24,
                "tracks": [
                    _track(id="v", type_="video", clips=[_clip(id="v1", type_="video", media_id=5)]),
                    _track(
                        id="h",
                        type_="video",
                        hidden=True,
                        clips=[_clip(id="v2", type_="video", media_id=6)],
                    ),
                    _track(
                        id="ha",
                        type_="audio",
                        hidden=True,
                        clips=[_clip(id="a1", type_="audio", media_id=7)],
                    ),
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert len(plan.video_clips) == 1
        assert plan.audio_clips == []
        assert plan.final_duration == 2

    def test_audio_only_duration_from_audio(self):
        design = {
            "version": 2,
            "format": {"width": 1080, "height": 1350},
            "timeline": {
                "fps": 30,
                "tracks": [
                    _track(
                        id="a",
                        type_="audio",
                        clips=[_clip(id="a1", type_="audio", media_id=9, duration=5)],
                    )
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert plan.final_duration == 5
        assert plan.video_clips == []

    def test_background_color_from_design(self):
        design = {
            "version": 2,
            "format": {"width": 720, "height": 1280},
            "background": {"color": "#204060"},
            "timeline": {
                "fps": 30,
                "tracks": [
                    _track(id="v", type_="video", clips=[_clip(id="v1", type_="video", media_id=1)])
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert plan.background_color == "#204060"

    def test_gap_increases_final_duration(self):
        design = {
            "version": 2,
            "format": {"width": 720, "height": 1280},
            "timeline": {
                "fps": 30,
                "tracks": [
                    _track(
                        id="v",
                        type_="video",
                        clips=[
                            _clip(id="v1", type_="video", media_id=1, start=0, duration=2),
                            _clip(id="v2", type_="video", media_id=2, start=5, duration=3),
                        ],
                    )
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert plan.final_duration == 8

    def test_audio_only_plan_has_no_video(self):
        design = {
            "version": 2,
            "format": {"width": 720, "height": 1280},
            "timeline": {
                "fps": 30,
                "tracks": [
                    _track(id="a", type_="audio", clips=[_clip(id="a1", type_="audio", media_id=9)])
                ],
            },
        }
        plan = _service().build_final_plan(design)
        assert plan.video_clips == []


class TestVideoSegmentsGaps:
    def _plan(self, clips, final_duration, bg="#111111"):
        return FinalRenderPlan(
            version=2,
            platform="instagram",
            media_type="feed_45",
            width=720,
            height=1280,
            fps=30,
            final_duration=final_duration,
            video_clips=clips,
            audio_clips=[],
            background_color=bg,
        )

    def _clip(self, start, duration, media_id=1):
        return FinalClip(
            track_id="v",
            clip_id=f"c{start}",
            start=start,
            duration=duration,
            media_id=media_id,
            source="forgeai",
            in_point=0,
            out_point=duration,
            rotation=0.0,
            crop=None,
            mute=False,
            volume=1.0,
            fade_in=0.0,
            fade_out=0.0,
            ducking_enabled=False,
            ducking_level=1.0,
        )

    def test_lead_gap_mid_gap_trail(self):
        plan = self._plan(
            [
                self._clip(2, 3),
                self._clip(7, 2),
            ],
            final_duration=12,
        )
        segments = _service()._video_segments(plan)
        assert [(c is None, round(d, 3)) for c, d in segments] == [
            (True, 2.0),  # lead-in
            (False, 3.0),
            (True, 2.0),  # mid gap 5→7
            (False, 2.0),
            (True, 3.0),  # trail 11→12
        ]

    def test_no_pad_when_contiguous_full(self):
        plan = self._plan([self._clip(0, 5)], final_duration=5)
        segments = _service()._video_segments(plan)
        assert len(segments) == 1
        assert segments[0][0] is not None
        assert segments[0][1] == 5

    def test_single_clip_start_zero_trailing_pad_from_audio(self):
        plan = self._plan([self._clip(0, 3)], final_duration=6)
        segments = _service()._video_segments(plan)
        assert len(segments) == 2
        assert segments[0][0] is not None
        assert segments[1][0] is None
        assert segments[1][1] == pytest.approx(3.0)


class TestVideoFilterCrop:
    def _vf(self, crop=None, rotation=0.0):
        plan = FinalRenderPlan(
            version=2,
            platform="instagram",
            media_type="feed_45",
            width=720,
            height=1280,
            fps=30,
            final_duration=1,
            video_clips=[],
            audio_clips=[],
        )
        clip = FinalClip(
            track_id="v",
            clip_id="c",
            start=0,
            duration=1,
            media_id=1,
            source="forgeai",
            in_point=0,
            out_point=1,
            rotation=rotation,
            crop=crop,
            mute=False,
            volume=1.0,
            fade_in=0.0,
            fade_out=0.0,
            ducking_enabled=False,
            ducking_level=1.0,
        )
        return StudioRenderService._video_vf(clip, plan)

    def test_crop_uses_source_ratios(self):
        vf = self._vf({"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.5})
        assert "crop=iw*0.5:ih*0.5:iw*0.1:ih*0.2" in vf
        # jamais multiplié par le format de sortie
        assert "720" not in vf.split("crop=")[1].split(",")[0]
        assert "1280" not in vf.split("crop=")[1].split(",")[0]
        assert "scale=720:1280" in vf

    def test_no_crop_scale_only(self):
        vf = self._vf(None)
        assert "crop=" not in vf
        assert vf.startswith("scale=720:1280")


class TestFfmpegColor:
    def test_hex(self):
        assert _ffmpeg_color("#101010") == "0x101010"
        assert _ffmpeg_color("abc") == "0xaabbcc"
        assert _ffmpeg_color(None) == "0x111111"
        assert _ffmpeg_color("not-a-color") == "0x111111"


class TestCleanup:
    def test_orphan_temp_respects_prefix_and_age(self, tmp_path, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        old = tmp_path / "forgeai-studio-render-old"
        old.mkdir()
        ancient = time.time() - 999999
        import os

        os.utime(old, (ancient, ancient))
        recent = tmp_path / "forgeai-studio-render-recent"
        recent.mkdir()
        unrelated = tmp_path / "other-dir"
        unrelated.mkdir()
        media_like = tmp_path / "forgeai-studio-notprefix"
        media_like.mkdir()

        removed = cleanup_orphan_studio_temps(max_age_seconds=3600)
        assert str(old) in removed
        assert not old.exists()
        assert recent.exists()
        assert unrelated.exists()

        # âge négatif / 0 → pas de nettoyage forcé dangereux
        removed2 = cleanup_orphan_studio_temps(max_age_seconds=0)
        assert removed2 == []
        assert recent.exists()

    def test_cleanup_never_touches_storage_path(self, tmp_path, monkeypatch):
        storage = tmp_path / "photos"
        storage.mkdir()
        studio = storage / "studio_renders" / "25"
        studio.mkdir(parents=True)
        valid = studio / "keep.mp4"
        valid.write_bytes(b"x")
        old = time.time() - 999999
        import os

        os.utime(valid, (old, old))

        # on force le temp root à être le parent : le guard storage doit bloquer
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        # aussi un fake forgeai-studio-* sous storage (ne doit jamais partir)
        fake = storage / "forgeai-studio-render-x"
        fake.mkdir()
        os.utime(fake, (old, old))

        removed = cleanup_orphan_studio_temps(max_age_seconds=1)
        assert str(fake) not in removed
        assert fake.exists()
        assert valid.exists()

    def test_retention_deletes_only_old_mp4(self, tmp_path, monkeypatch):
        from app.core.config import get_settings
        from app.services.photo import storage as photo_storage

        root = tmp_path / "photos"
        (root / "studio_renders" / "1").mkdir(parents=True)
        (root / "studio_renders" / "2").mkdir(parents=True)
        old_mp4 = root / "studio_renders" / "1" / "old.mp4"
        new_mp4 = root / "studio_renders" / "2" / "new.mp4"
        old_mp4.write_bytes(b"old")
        new_mp4.write_bytes(b"new")
        ancient = time.time() - 40 * 86400
        import os

        os.utime(old_mp4, (ancient, ancient))

        settings = get_settings()
        monkeypatch.setattr(settings, "STUDIO_RENDER_RETENTION_DAYS", 30)

        _FakeStorage = type("_FakeStorage", (), {"root": root})
        # cleanup_expired_renders importe get_photo_storage au niveau module
        import app.services.studio_render as sr

        monkeypatch.setattr(sr, "get_photo_storage", lambda: _FakeStorage())

        removed = cleanup_expired_renders()
        assert removed == 1
        assert not old_mp4.exists()
        assert new_mp4.exists()

        # 0 = indéfini
        monkeypatch.setattr(settings, "STUDIO_RENDER_RETENTION_DAYS", 0)
        assert cleanup_expired_renders() == 0
        assert new_mp4.exists()


class TestProgressPayload:
    def test_photo_job_progress_property(self):
        from app.models.photo import PhotoJob

        job = PhotoJob(
            id="j1",
            type="studio_render",
            status="running",
            payload_json={"progress": {"stage": "video", "percent": 30}},
            attempts=1,
        )
        assert job.progress == {"stage": "video", "percent": 30}
        job.payload_json = None
        assert job.progress is None
        job.payload_json = {"progress": "bad"}
        assert job.progress is None

    def test_schema_exposes_progress(self):
        from app.schemas.photos import PhotoJobResponse

        job_fields = PhotoJobResponse.model_fields
        assert "progress" in job_fields

    def test_create_request_schema(self):
        from app.schemas.photos import StudioRenderCreateRequest

        req = StudioRenderCreateRequest(publication_id=42)
        assert req.publication_id == 42
