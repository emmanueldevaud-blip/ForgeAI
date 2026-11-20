"""Tests Studio : musique Instagram (re)choisie à chaque changement de photo."""

from datetime import UTC, datetime

import pytest

from app.models.photo import Photo
from app.schemas.sport import PublicationDraftUpdate
from app.services.community_manager.studio import CommunityManagerStudioService
from tests.community_manager.test_studio_caption_sync import _make_garmin_publication

_FAKE_ENTRY = {
    "source": "instagram",
    "status": "selected",
    "audio_id": "999888777",
    "title": "Running Through The Night",
    "artist": "Fake Artist",
    "query": "night run",
    "raison": "thème nocturne",
}


async def _make_photo(db_session, user) -> Photo:
    photo = Photo(
        owner_id=user.id,
        original_filename="paysage.jpg",
        storage_path="2026/11/paysage.jpg",
        mime_type="image/jpeg",
        taken_at=datetime.now(UTC),
        content_hash="c" * 64,
    )
    db_session.add(photo)
    await db_session.commit()
    return photo


class TestStudioIgMusicHook:

    @pytest.mark.asyncio
    async def test_photo_selection_persists_ig_audio(self, db_session, auth_user, monkeypatch):
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo = await _make_photo(db_session, auth_user)

        captured = {}

        async def fake_pick(db, user, photo_id, title=None, hashtags=None):
            captured["photo_id"] = photo_id
            captured["title"] = title
            return dict(_FAKE_ENTRY)

        monkeypatch.setattr(
            "app.services.community_manager.ig_music.pick_audio_for_photo_bounded",
            fake_pick,
        )

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=photo.id))

        assert captured["photo_id"] == photo.id
        assert captured["title"] == "Sortie longue"
        assert updated.design is not None
        assert updated.design["ig_audio"]["audio_id"] == "999888777"
        assert updated.design["ig_audio"]["title"] == "Running Through The Night"

    @pytest.mark.asyncio
    async def test_photo_removal_clears_ig_audio(self, db_session, auth_user, monkeypatch):
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo = await _make_photo(db_session, auth_user)

        async def fake_pick(db, user, photo_id, title=None, hashtags=None):
            return dict(_FAKE_ENTRY)

        monkeypatch.setattr(
            "app.services.community_manager.ig_music.pick_audio_for_photo_bounded",
            fake_pick,
        )

        await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=photo.id))
        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=None))

        assert updated.design is None or "ig_audio" not in (updated.design or {})

    @pytest.mark.asyncio
    async def test_pick_failure_keeps_publication_usable(self, db_session, auth_user, monkeypatch):
        """Un échec de choix musique ne doit jamais bloquer la sélection de photo."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo = await _make_photo(db_session, auth_user)

        async def failing_pick(db, user, photo_id, title=None, hashtags=None):
            raise RuntimeError("IA indisponible")

        monkeypatch.setattr(
            "app.services.community_manager.ig_music.pick_audio_for_photo_bounded",
            failing_pick,
        )

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=photo.id))

        assert updated.photo_id == photo.id
        assert updated.design is None or "ig_audio" not in (updated.design or {})

    @pytest.mark.asyncio
    async def test_ig_audio_configuration_built_from_design(self, db_session, auth_user):
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        # Sans musique : pas de configuration
        assert service._ig_audio_configuration(pub) is None

        # Avec musique : audio_configuration pour la publication du Reel
        pub.design = {"ig_audio": {"audio_id": "587784541076604", "title": "Song"}}
        cfg = service._ig_audio_configuration(pub)
        assert cfg == {
            "audio_id": "587784541076604",
            "audio_volume": 100,
            "video_volume": 1,
        }


class TestStudioPhotoSelection:
    """Selection multi-photos (diaporama) : carrousel + musique sur la couverture."""

    @pytest.mark.asyncio
    async def test_photo_ids_set_carousel_and_cover(self, db_session, auth_user, monkeypatch):
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo = await _make_photo(db_session, auth_user)

        async def fake_pick(db, user, photo_id, title=None, hashtags=None):
            return dict(_FAKE_ENTRY)

        monkeypatch.setattr(
            "app.services.community_manager.ig_music.pick_audio_for_photo_bounded",
            fake_pick,
        )

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_ids=[photo.id]))

        assert updated.design["carousel"] == [photo.id]
        assert updated.photo_id == photo.id
        assert updated.design["ig_audio"]["audio_id"] == "999888777"

    @pytest.mark.asyncio
    async def test_photo_ids_order_preserved_and_music_uses_cover(self, db_session, auth_user, monkeypatch):
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo_a = await _make_photo(db_session, auth_user)
        photo_b = await _make_photo(db_session, auth_user)

        captured = {}

        async def fake_pick(db, user, photo_id, title=None, hashtags=None):
            captured["photo_id"] = photo_id
            return dict(_FAKE_ENTRY)

        monkeypatch.setattr(
            "app.services.community_manager.ig_music.pick_audio_for_photo_bounded",
            fake_pick,
        )

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_ids=[photo_a.id, photo_b.id]))

        assert updated.design["carousel"] == [photo_a.id, photo_b.id]
        assert updated.photo_id == photo_a.id
        assert captured["photo_id"] == photo_a.id
        assert updated.design["ig_audio"]["audio_id"] == "999888777"

    @pytest.mark.asyncio
    async def test_photo_ids_filters_unavailable_and_dedupes(self, db_session, auth_user):
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo = await _make_photo(db_session, auth_user)

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_ids=[photo.id, photo.id, 999999]))

        assert updated.design["carousel"] == [photo.id]
        assert updated.photo_id == photo.id

    @pytest.mark.asyncio
    async def test_same_photo_ids_keep_selected_music(self, db_session, auth_user, monkeypatch):
        """Renvoyer les mêmes photo_ids (publication) ne doit pas remplacer la musique choisie."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        photo = await _make_photo(db_session, auth_user)
        selected = {
            "source": "instagram",
            "status": "selected",
            "audio_id": "chosen-by-user",
            "title": "Ma musique",
            "artist": "Artiste",
        }

        async def fake_pick(db, user, photo_id, title=None, hashtags=None, **kwargs):
            return dict(_FAKE_ENTRY)

        monkeypatch.setattr(
            "app.services.community_manager.ig_music.pick_audio_for_photo_bounded",
            fake_pick,
        )

        await service.update_draft(
            pub.id,
            PublicationDraftUpdate(photo_ids=[photo.id], design={"ig_audio": dict(selected)}),
        )
        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_ids=[photo.id]))

        assert updated.design["ig_audio"]["audio_id"] == "chosen-by-user"
        assert updated.design["ig_audio"]["title"] == "Ma musique"
