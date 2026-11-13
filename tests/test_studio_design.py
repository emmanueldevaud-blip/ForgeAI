"""Persistance du design de l'éditeur graphique du Studio.

Vérifie le parcours frontend -> PATCH -> backend -> base -> GET
pour la colonne design de sport_publications.
"""

import pytest
from sqlalchemy import select

from app.models.sport import SportPublication
from tests.test_studio_story_flow import _make_story_draft

DESIGN = {
    "version": 1,
    "format": {"platform": "instagram", "type": "feed_45", "width": 1080, "height": 1350},
    "background": {"color": "#101010"},
    "elements": [
        {
            "id": "el-1",
            "type": "image",
            "photoId": 12,
            "x": 0,
            "y": 0,
            "w": 1080,
            "h": 1350,
            "rotation": 0,
            "filter": "sepia(60%)",
            "crop": {"x": 0, "y": 0, "w": 1, "h": 1},
        },
        {
            "id": "el-2",
            "type": "text",
            "text": "Bonjour 🏃",
            "x": 80,
            "y": 900,
            "w": 900,
            "h": 120,
            "rotation": -4,
            "font": "Arial",
            "size": 64,
            "color": "#ffffff",
            "align": "center",
            "bold": True,
            "italic": False,
            "shadow": True,
        },
        {
            "id": "el-3",
            "type": "sticker",
            "sticker": "🔥",
            "x": 500,
            "y": 200,
            "w": 160,
            "h": 160,
            "rotation": 12,
        },
    ],
    "carousel": [12, 15],
    "cover": 12,
}


class TestStudioDesignPersistence:
    @pytest.mark.asyncio
    async def test_patch_design_persiste_et_renvoi(
        self, db_session, client, admin_headers, admin_user
    ):
        pub, _entry = await _make_story_draft(db_session, admin_user)
        pub_id = pub.id

        patch = await client.patch(
            f"/community-manager/studio/draft/{pub_id}",
            json={"design": DESIGN},
            headers=admin_headers,
        )
        assert patch.status_code == 200
        assert patch.json()["design"] == DESIGN

        # Relecture depuis la base (nouvelle session de lecture)
        db_session.expire_all()
        row = await db_session.execute(
            select(SportPublication).where(SportPublication.id == pub_id)
        )
        persisted = row.scalar_one().design
        assert persisted == DESIGN
        assert persisted["elements"][1]["text"] == "Bonjour 🏃"
        assert persisted["format"]["type"] == "feed_45"

        get = await client.get(
            f"/community-manager/studio/draft/{pub_id}", headers=admin_headers
        )
        assert get.status_code == 200
        assert get.json()["design"] == DESIGN

    @pytest.mark.asyncio
    async def test_design_nul_par_defaut_et_absent_inchange(
        self, db_session, client, admin_headers, admin_user
    ):
        pub, _entry = await _make_story_draft(db_session, admin_user)
        pub_id = pub.id

        get = await client.get(
            f"/community-manager/studio/draft/{pub_id}", headers=admin_headers
        )
        assert get.status_code == 200
        assert get.json()["design"] is None

        # Un PATCH sans design ne touche pas au design existant
        await client.patch(
            f"/community-manager/studio/draft/{pub_id}",
            json={"design": DESIGN},
            headers=admin_headers,
        )
        await client.patch(
            f"/community-manager/studio/draft/{pub_id}",
            json={"title": "Nouveau titre"},
            headers=admin_headers,
        )
        get2 = await client.get(
            f"/community-manager/studio/draft/{pub_id}", headers=admin_headers
        )
        assert get2.json()["design"] == DESIGN
        assert get2.json()["title"] == "Nouveau titre"

    @pytest.mark.asyncio
    async def test_design_carrousel_sans_impact_v1(
        self, db_session, client, admin_headers, admin_user
    ):
        """Une publication V1 sans design reste inchangée (GET renvoie null)."""
        from tests.test_studio_story_flow import _make_v1_publication

        pub = await _make_v1_publication(db_session, admin_user)
        pub_id = pub.id

        get = await client.get(
            f"/community-manager/studio/draft/{pub_id}", headers=admin_headers
        )
        assert get.status_code == 200
        assert get.json()["design"] is None
        assert get.json()["calendar_entry"] is None
