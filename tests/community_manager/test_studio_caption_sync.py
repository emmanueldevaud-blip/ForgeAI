"""Tests synchronisation texte / aperçu des publications Garmin (Community Manager Studio).

Couvre la construction de la légende complète (titre + hashtags) et la cohérence
entre le champ texte éditable, l'aperçu et la régénération.
"""

from datetime import UTC, datetime
from inspect import signature

import pytest
from sqlalchemy import func, select

from app.models.photo import Photo
from app.models.sport import SportPublication
from app.schemas.sport import PublicationDraftUpdate, SportPublicationGenerateRequest
from app.services.ai_gateway import ai_gateway
from app.services.community_manager.studio import CommunityManagerStudioService, build_full_caption
from app.services.garmin import SportGarminConnectService
from app.services.sport_publications import SportPublicationService
from tests.test_calendar_suggestions import _make_activity, _make_athlete

# ============================================================
# Construction de la légende complète
# ============================================================

def test_build_full_caption_assembles_title_then_hashtags():
    """La légende complète = titre + ligne vide + hashtags (l'accroche est sur la photo)."""
    caption = build_full_caption("Sortie 10 km", "Belle sortie !", "#trail #running")

    assert caption == "Sortie 10 km\n\n#trail #running"


def test_build_full_caption_has_single_title_and_trailing_hashtags():
    """Le titre doit apparaître une seule fois et les hashtags en fin de texte."""
    caption = build_full_caption("Titre", "Accroche", "#a #b")

    assert caption.startswith("Titre")
    assert caption.endswith("#a #b")
    assert caption.count("Titre") == 1
    assert caption.count("#a") == 1


# ============================================================
# Helpers
# ============================================================

async def _make_garmin_publication(db_session, user):
    """Publication sportive Garmin type V1 : liée à une activité, titre + accroche + hashtags."""
    athlete = await _make_athlete(db_session, user)
    activity = await _make_activity(db_session, athlete, name="Sortie longue")
    pub = SportPublication(
        athlete_id=athlete.id,
        activity_id=activity.id,
        calendar_entry_id=None,
        status="draft",
        source="garmin",
        content_type="publication_sportive",
        title="Sortie longue",
        content="Belle sortie de 10 km avec un dénivelé correct.",
        hashtags="#trail #running",
    )
    db_session.add(pub)
    await db_session.commit()
    return pub


# ============================================================
# Tests : légende, aperçu, édition, photo, régénération
# ============================================================

class TestStudioCaptionSynchronisation:
    """Synchronisation entre le champ texte éditable et l'aperçu Garmin."""

    @pytest.mark.asyncio
    async def test_generation_stores_title_content_and_hashtags(self, db_session, auth_user, monkeypatch):
        """Une génération avec titre, accroche et hashtags produit une légende complète propre."""

        async def fake_generate(**kwargs):
            class FakeResp:
                text = (
                    '{"proposals": ['
                    '{"title": "Sortie 10 km", "content": "J\'avais prévu une petite sortie tranquille.", "hashtags": "#trail #running"}'
                    ']}'
                )
            return FakeResp()

        monkeypatch.setattr(ai_gateway, "generate", fake_generate)

        athlete = await _make_athlete(db_session, auth_user)
        activity = await _make_activity(db_session, athlete, name="Sortie 10 km")
        service = SportPublicationService(db_session, auth_user)
        pub = await service.generate(
            activity.id,
            SportPublicationGenerateRequest(styles=["stats"]),
        )

        assert pub.title == "Sortie 10 km"
        assert pub.content == "J'avais prévu une petite sortie tranquille."
        assert pub.hashtags == "#trail #running"

        full_caption = build_full_caption(pub.title, pub.content, pub.hashtags)
        assert full_caption == "Sortie 10 km\n\n#trail #running"

    @pytest.mark.asyncio
    async def test_preview_contains_full_caption_unique_title_and_trailing_hashtags(
        self, db_session, auth_user
    ):
        """L'aperçu doit afficher la légende complète : titre unique + hashtags en fin de texte."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        preview = await service.get_preview(pub.id, "feed")
        html = preview["preview_html"]

        assert "Sortie longue" in html
        # Le titre ne doit pas être dupliqué (overlay + texte)
        assert html.count("Sortie longue") == 1
        # Les hashtags doivent être présents dans le rendu
        assert "#trail #running" in html
        # L'accroche n'est plus dans la légende (elle est portée par la photo)
        assert "Belle sortie" not in html

    @pytest.mark.asyncio
    async def test_preview_reflects_manual_text_edition(self, db_session, auth_user):
        """Une modification manuelle du texte doit être répercutée dans l'aperçu."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        updated = await service.update_draft(
            pub.id, PublicationDraftUpdate(title="Nouveau titre", hashtags="#newtag")
        )
        await db_session.refresh(pub)

        preview = await service.get_preview(pub.id, "feed")
        html = preview["preview_html"]

        assert updated.title == "Nouveau titre"
        assert updated.hashtags == "#newtag"
        assert "Nouveau titre" in html
        assert "#newtag" in html
        assert "Sortie longue" not in html

    @pytest.mark.asyncio
    async def test_photo_change_keeps_hashtags(self, db_session, auth_user):
        """Un changement de photo ne doit pas perdre les hashtags du champ texte."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(hashtags="#preserve"))
        assert updated.hashtags == "#preserve"

        photo = Photo(
            owner_id=auth_user.id,
            original_filename="paysage.jpg",
            storage_path="2026/11/paysage.jpg",
            mime_type="image/jpeg",
            taken_at=datetime.now(UTC),
            content_hash="c" * 64,
        )
        db_session.add(photo)
        await db_session.commit()

        updated = await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=photo.id))
        await db_session.refresh(pub)

        assert updated.hashtags == "#preserve"

    @pytest.mark.asyncio
    async def test_regenerate_does_not_duplicate_title_or_hashtags(self, db_session, auth_user, monkeypatch):
        """Une régénération ne doit pas dupliquer le titre ni les hashtags."""

        async def fake_generate(**kwargs):
            class FakeResp:
                text = (
                    '{"proposals": ['
                    '{"title": "Titre Regen", "content": "Accroche regen.", "hashtags": "#trail"}'
                    ']}'
                )
            return FakeResp()

        monkeypatch.setattr(ai_gateway, "generate", fake_generate)

        pub = await _make_garmin_publication(db_session, auth_user)
        regen_service = SportGarminConnectService(db_session)
        result = await regen_service.regenerate_publication_content(pub.id, auth_user)
        assert result is not None

        await db_session.refresh(pub)
        full_caption = build_full_caption(pub.title, pub.content, pub.hashtags)
        assert full_caption == "Titre Regen\n\n#trail"
        assert full_caption.count("Titre Regen") == 1
        assert full_caption.count("#trail") == 1


# ============================================================
# Tests : aucun enregistrement dans le module photo avant publication
# ============================================================

class TestNoOverlayRegistrationBeforePublication:
    """L'overlay sport ne doit créer une Photo que lors de la publication (Instagram / Facebook)."""

    @staticmethod
    def _spy(service, calls: list) -> None:
        original = service._ensure_sport_defaults

        async def spy(pub, persist_overlay=True):
            calls.append(persist_overlay)
            return await original(pub, persist_overlay=persist_overlay)

        service._ensure_sport_defaults = spy

    @pytest.mark.asyncio
    async def test_get_preview_does_not_persist_overlay(self, db_session, auth_user):
        """L'aperçu ne doit jamais enregistrer l'overlay dans le module photo."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        calls: list = []
        self._spy(service, calls)

        await service.get_preview(pub.id, "feed")

        assert calls, "get_preview doit passer par _ensure_sport_defaults"
        assert all(persist is False for persist in calls)

    @pytest.mark.asyncio
    async def test_photo_selection_does_not_create_photo(self, db_session, auth_user):
        """Sélectionner une photo ne crée aucune entrée dans le module photo."""
        pub = await _make_garmin_publication(db_session, auth_user)
        photo = Photo(
            owner_id=auth_user.id,
            original_filename="selection.jpg",
            storage_path="2026/11/selection.jpg",
            mime_type="image/jpeg",
            taken_at=datetime.now(UTC),
            content_hash="a" * 64,
        )
        db_session.add(photo)
        await db_session.commit()

        service = CommunityManagerStudioService(db_session, auth_user)
        calls: list = []
        self._spy(service, calls)

        await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=photo.id))

        assert calls and all(persist is False for persist in calls)
        count = await db_session.scalar(
            select(func.count()).select_from(Photo).where(Photo.owner_id == auth_user.id)
        )
        assert count == 1, "aucune Photo supplémentaire ne doit être enregistrée avant publication"

    @pytest.mark.asyncio
    async def test_ensure_sport_defaults_keeps_persist_default(self, db_session, auth_user):
        """Les chemins de publication (Instagram / Facebook) conservent l'enregistrement par défaut."""
        sig = signature(CommunityManagerStudioService._ensure_sport_defaults)
        assert sig.parameters["persist_overlay"].default is True

        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        await service._ensure_sport_defaults(pub)
        # appel sans argument explicite -> comportement inchangé (défaut True)
        assert sig.parameters["persist_overlay"].default is True


# ============================================================
# Tests : aperçu lisible + stats visibles sur l'image
# ============================================================

class TestPreviewStatsAndReadability:
    """L'aperçu doit afficher les stats sur l'image et rester lisible en thème sombre."""

    @pytest.mark.asyncio
    async def test_feed_preview_sets_explicit_dark_text_color(self, db_session, auth_user):
        """La carte de l'aperçu impose une couleur de texte sombre (sinon texte blanc hérité du thème sombre sur carte blanche)."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        preview = await service.get_preview(pub.id, "feed")

        assert "color: #111827" in preview["preview_html"]

    @pytest.mark.asyncio
    async def test_feed_preview_shows_stats_panel_over_photo(self, db_session, auth_user):
        """Les stats Garmin apparaissent sur l'image dans un panneau sombre (texte blanc lisible)."""
        pub = await _make_garmin_publication(db_session, auth_user)
        photo = Photo(
            owner_id=auth_user.id,
            original_filename="paysage.jpg",
            storage_path="2026/11/paysage.jpg",
            mime_type="image/jpeg",
            taken_at=datetime.now(UTC),
            content_hash="d" * 64,
        )
        db_session.add(photo)
        await db_session.commit()

        service = CommunityManagerStudioService(db_session, auth_user)
        await service.update_draft(pub.id, PublicationDraftUpdate(photo_id=photo.id))
        preview = await service.get_preview(pub.id, "feed")
        html = preview["preview_html"]

        assert "DISTANCE" in html and "10.0 km" in html
        assert "DÉNIVELÉ" in html and "200 m D+" in html
        assert "TEMPS" in html and "1h00" in html
        # Panneau semi-transparent derrière le texte blanc
        assert "rgba(0,0,0,0.72)" in html
        assert "color:#ffffff" in html.replace(" ", "")
        # Stats en petit + signature avec dièse
        assert "font-size:15px" in html and "font-size:9px" in html
        assert "#Jepepagtrail" in html

    @pytest.mark.asyncio
    async def test_feed_preview_without_photo_has_no_stats_panel(self, db_session, auth_user):
        """Sans photo sélectionnée, aucun panneau de stats (fidèle à la publication)."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        html = (await service.get_preview(pub.id, "feed"))["preview_html"]

        assert "DISTANCE" not in html
        assert "rgba(0,0,0,0.72)" not in html


# ============================================================
# Tests : adaptation du cadrage a tous les formats
# ============================================================

class TestPreviewFormatAdaptation:
    """L'aperçu doit s'adapter au ratio du design (portrait, carre, paysage, story)."""

    @pytest.mark.asyncio
    async def test_feed_preview_uses_design_aspect_ratio(self, db_session, auth_user):
        """Conteneur image en aspect-ratio issu du design (défaut 1080x1350), sans hauteur fixe."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        html = (await service.get_preview(pub.id, "feed"))["preview_html"]

        assert "aspect-ratio: 1080/1350" in html
        assert "height: 480px" not in html

    @pytest.mark.asyncio
    async def test_feed_preview_adapts_to_custom_format(self, db_session, auth_user):
        """Un format personnalisé (ici carré) du design est respecté."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)
        await service.update_draft(
            pub.id, PublicationDraftUpdate(design={"format": {"width": 1080, "height": 1080}})
        )

        html = (await service.get_preview(pub.id, "feed"))["preview_html"]

        assert "aspect-ratio: 1080/1080" in html

    @pytest.mark.asyncio
    async def test_story_preview_is_fluid_not_fixed(self, db_session, auth_user):
        """L'aperçu story abandonne les dimensions fixes 1080x1920 au profit d'un conteneur fluide 9/16."""
        pub = await _make_garmin_publication(db_session, auth_user)
        service = CommunityManagerStudioService(db_session, auth_user)

        html = (await service.get_preview(pub.id, "story"))["preview_html"]

        assert "width: 1080px" not in html
        assert "height: 1920px" not in html
        assert "aspect-ratio: 9/16" in html
