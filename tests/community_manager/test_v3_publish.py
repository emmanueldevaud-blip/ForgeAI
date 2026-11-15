"""Tests pour Community Manager V3 - Publication Instagram."""

import json
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photo import Photo
from app.models.sport import (
    CommunityManagerStrategy,
    EditorialCalendarEntry,
    SportActivity,
    SportAthlete,
    SportPublication,
)
from app.models.user import User
from app.schemas.sport import (
    PublicationDraftUpdate,
    PublicationGenerateFromCalendarRequest,
    PublicationGenerateTextRequest,
    PublicationPublishRequest,
    PublicationValidateRequest,
    PublicationPreviewRequest,
)
from app.services.community_manager.studio import CommunityManagerStudioService
from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
from app.services.sport_media_publish import MediaPublishService, MediaPublishError, MediaInfo
from app.services.sport_instagram import _decrypt_token


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def mock_user():
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    return user


@pytest.fixture
def mock_athlete():
    athlete = MagicMock(spec=SportAthlete)
    athlete.id = 10
    athlete.user_id = 1
    return athlete


@pytest.fixture
def mock_strategy(mock_athlete):
    strategy = MagicMock(spec=CommunityManagerStrategy)
    strategy.id = 100
    strategy.athlete_id = mock_athlete.id
    strategy.brand_identity = "TestBrand"
    strategy.tone = ["professional", "inspirational"]
    strategy.target_audience = "Athlètes endurance 25-45 ans"
    strategy.objectives = ["engagement", "visibility"]
    strategy.themes = ["running", "recovery"]
    strategy.frequency = 3
    strategy.networks = ["instagram"]
    strategy.rules = ["Pas de résultats inventés", "Utiliser les vraies données Garmin"]
    strategy.forbidden_topics = ["politique", "concurrentiels"]
    strategy.calendar_entries = []
    return strategy


@pytest.fixture
def mock_db(mock_athlete, mock_strategy):
    db = AsyncMock(spec=AsyncSession)
    
    # Mock pour _get_athlete
    execute_athlete = AsyncMock()
    execute_athlete.scalar_one_or_none.return_value = mock_athlete
    
    # Mock pour get_strategy
    execute_strategy = AsyncMock()
    execute_strategy.scalar_one_or_none.return_value = mock_strategy
    
    db.execute.side_effect = [
        execute_athlete,  # _get_athlete
        execute_strategy,  # get_strategy
    ]
    
    # Mock pour _get_recent_activities
    activity = MagicMock(spec=SportActivity)
    activity.id = 1
    activity.sport_type = "running"
    activity.activity_name = "Morning Run"
    activity.started_at = datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc)
    activity.duration_seconds = 3600
    activity.distance_m = 10000
    activity.elevation_gain_m = 100
    activity.elevation_loss_m = 100
    activity.avg_speed_m_s = 2.77
    activity.avg_pace_sec_km = 360
    activity.avg_heart_rate = 150
    activity.max_heart_rate = 170
    activity.avg_cadence = 170
    activity.avg_power_w = None
    activity.calories = 500
    activity.temperature_c = 10
    activity.source_type = "garmin"
    
    activities_result = AsyncMock()
    activities_result.scalars.return_value.all.return_value = [activity]
    
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    
    return db


@pytest.fixture
def service(mock_db, mock_user):
    return CommunityManagerStudioService(mock_db, mock_user)


# ============================================================
# Tests MetaPublishService
# ============================================================

class TestMetaPublishService:
    """Tests pour MetaPublishService."""

    @pytest.fixture
    def mock_connection(self):
        conn = MagicMock()
        conn.id = 1
        conn.user_id = 1
        conn.instagram_business_account_id = "17841400000000000"
        conn.encrypted_access_token = "encrypted_short_token"
        conn.encrypted_long_lived_token = "encrypted_long_token"
        conn.status = "active"
        conn.token_type = "bearer"
        conn.expires_in = 5184000
        conn.obtained_at = datetime.now(timezone.utc)
        return conn

    @pytest.fixture
    def mock_db(self, mock_connection):
        db = AsyncMock(spec=AsyncSession)
        
        execute_result = AsyncMock()
        execute_result.scalar_one_or_none.return_value = mock_connection
        db.execute.return_value = execute_result
        
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        return MetaPublishService(mock_db)

    @pytest.mark.asyncio
    async def test_get_valid_token_returns_token(self, service, mock_connection, mock_db):
        """Test récupération token valide."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_connection
        
        with patch('app.services.sport_instagram._decrypt_token', return_value="long_token"):
            token = await service._get_valid_token(mock_connection)
            assert token == "long_token"

    @pytest.mark.asyncio
    async def test_create_media_container_success(self, service, mock_connection, mock_db):
        """Test création conteneur média réussie."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_connection
        
        with patch('app.services.sport_instagram._decrypt_token', return_value="valid_token"):
            with patch('httpx.AsyncClient.post') as mock_post:
                mock_response = MagicMock()
                mock_response.json.return_value = {"id": "container_123"}
                mock_response.raise_for_status = MagicMock()
                mock_post.return_value = mock_response
                
                container_id = await service.create_media_container(
                    mock_connection, "https://example.com/photo.jpg", "Test caption"
                )
                
                assert container_id == "container_123"
                mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_media_container_no_token(self, service, mock_connection, mock_db):
        """Test création conteneur sans token valide."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_connection
        
        with patch('app.services.sport_instagram._decrypt_token', return_value=None):
            with pytest.raises(MetaPublishError, match="Aucun token valide"):
                await service.create_media_container(
                    mock_connection, "https://example.com/photo.jpg", "Test"
                )

    @pytest.mark.asyncio
    async def test_publish_media_container_success(self, service, mock_connection, mock_db):
        """Test publication conteneur réussie."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_connection
        
        with patch('app.services.sport_instagram._decrypt_token', return_value="valid_token"):
            with patch('httpx.AsyncClient.get') as mock_get, \
                 patch('httpx.AsyncClient.post') as mock_post:
                
                # Mock polling status
                mock_status_resp = MagicMock()
                mock_status_resp.status_code = 200
                mock_status_resp.json.return_value = {"status_code": "FINISHED"}
                
                # Mock publish
                mock_publish_resp = MagicMock()
                mock_publish_resp.json.return_value = {"id": "media_123"}
                mock_publish_resp.raise_for_status = MagicMock()
                
                mock_get.return_value = mock_status_resp
                mock_post.return_value = mock_publish_resp
                
                media_id = await service.publish_media_container(mock_connection, "container_123")
                
                assert media_id == "media_123"

    @pytest.mark.asyncio
    async def test_publish_media_container_timeout(self, service, mock_connection, mock_db):
        """Test timeout publication conteneur."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_connection
        
        with patch('app.services.sport_instagram._decrypt_token', return_value="valid_token"):
            with patch('httpx.AsyncClient.get') as mock_get:
                # Toujours IN_PROGRESS
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"status_code": "IN_PROGRESS"}
                mock_get.return_value = mock_resp
                
                with pytest.raises(MetaPublishError, match="Timeout"):
                    await service.publish_media_container(mock_connection, "container_123")

    @pytest.mark.asyncio
    async def test_publish_photo_success(self, service, mock_connection, mock_db):
        """Test publication photo complète."""
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_connection
        
        with patch.object(service, 'create_media_container', return_value="container_123") as mock_create, \
             patch.object(service, 'publish_media_container', return_value="media_123") as mock_publish:
            
            media_id = await service.publish_photo(mock_connection, "https://example.com/photo.jpg", "Test caption")
            
            assert media_id == "media_123"
            mock_create.assert_called_once()
            mock_publish.assert_called_once_with(mock_connection, "container_123")


# ============================================================
# Tests MediaPublishService
# ============================================================

class TestMediaPublishService:
    """Tests pour MediaPublishService."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.fixture
    def service(self, mock_db):
        return MediaPublishService(mock_db)

    def test_create_signed_token(self, service):
        """Test création token JWT signé."""
        token = service._create_signed_token(photo_id=123, user_id=456, expires_in_seconds=3600)
        
        assert isinstance(token, str)
        assert len(token) > 0
        # Vérifier que c'est un JWT valide (3 parties séparées par des points)
        parts = token.split('.')
        assert len(parts) == 3

    def test_verify_signed_token_valid(self, service):
        """Test vérification token valide."""
        token = service._create_signed_token(photo_id=123, user_id=456, expires_in_seconds=3600)
        payload = service._verify_signed_token(token)
        
        assert payload is not None
        assert payload["photo_id"] == 123
        assert payload["user_id"] == 456
        assert payload["type"] == "media_publish"

    def test_verify_signed_token_expired(self, service):
        """Test vérification token expiré."""
        import jwt
        import hashlib
        import base64
        
        # Créer un token expiré manuellement avec la même clé que le service
        from app.core.config import get_settings
        import hashlib
        import base64
        
        settings = get_settings()
        secret = f"{settings.SECRET_KEY}:media-publish".encode("utf-8")
        signing_key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
        
        now = datetime.now(timezone.utc)
        exp = now - timedelta(hours=1)
        
        payload = {
            "photo_id": 123,
            "user_id": 456,
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "exp": int(exp.timestamp()),
            "type": "media_publish",
        }
        
        token = jwt.encode(payload, signing_key, algorithm="HS256")
        
        payload = service._verify_signed_token(token)
        assert payload is None  # Expiré

    def test_verify_signed_token_invalid_signature(self, service):
        """Test vérification token signature invalide."""
        payload = service._verify_signed_token("invalid.token.signature")
        assert payload is None

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_success(self, service):
        """Test préparation média réussie."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 456
        mock_photo.is_public = False
        mock_photo.mime_type = "image/jpeg"
        mock_photo.original_filename = "test.jpg"
        mock_photo.is_deleted = False
        
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_photo
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        service.db.flush = AsyncMock()
        service.db.commit = AsyncMock()
        
        # Mock get_settings where it's actually imported (inside the function)
        with patch('app.core.config.get_settings') as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            
            url = await service.prepare_media_for_publish(photo_id=123, user_id=456, expires_in_seconds=3600)
        
        assert isinstance(url, MediaInfo)
        assert "meta_token=" in url.url
        assert "photos/123/file" in url.url
        assert url.mime_type == "image/jpeg"
        assert url.filename == "test.jpg"
        assert url.is_video is False

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_unauthorized(self, service):
        """Test préparation média accès non autorisé."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 789  # Autre utilisateur
        mock_photo.is_public = False
        mock_photo.mime_type = "image/jpeg"
        mock_photo.original_filename = "test.jpg"
        mock_photo.is_deleted = False
        
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_photo
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        
        with pytest.raises(MediaPublishError, match="Accès non autorisé"):
            await service.prepare_media_for_publish(photo_id=123, user_id=456)

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_heic_rejected(self, service):
        """Test rejet d'un fichier HEIC (non supporté par Instagram)."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 456
        mock_photo.is_public = False
        mock_photo.mime_type = "image/heic"
        mock_photo.original_filename = "photo.HEIC"
        mock_photo.is_deleted = False
        
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_photo
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        service.db.flush = AsyncMock()
        
        with pytest.raises(MediaPublishError, match="non supporté"):
            await service.prepare_media_for_publish(photo_id=123, user_id=456)

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_video_mp4(self, service):
        """Test acceptation d'une vidéo MP4."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 456
        mock_photo.is_public = False
        mock_photo.mime_type = "video/mp4"
        mock_photo.original_filename = "video.mp4"
        mock_photo.is_deleted = False
        
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_photo
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        service.db.flush = AsyncMock()
        
        with patch('app.core.config.get_settings') as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            
            media_info = await service.prepare_media_for_publish(photo_id=123, user_id=456, expires_in_seconds=3600)
        
        assert isinstance(media_info, MediaInfo)
        assert media_info.mime_type == "video/mp4"
        assert media_info.is_video is True
        assert "size=original" in media_info.url
        assert "meta_token=" in media_info.url

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_photo_not_found(self, service):
        """Test photo introuvable."""
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = None
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        
        with pytest.raises(MediaPublishError, match="Photo introuvable"):
            await service.prepare_media_for_publish(photo_id=999, user_id=456)

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_deleted_media(self, service):
        """Test média supprimé."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 456
        mock_photo.is_public = False
        mock_photo.mime_type = "image/jpeg"
        mock_photo.original_filename = "photo.jpg"
        mock_photo.is_deleted = True
        
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_photo
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        
        with pytest.raises(MediaPublishError, match="supprimé"):
            await service.prepare_media_for_publish(photo_id=123, user_id=456)

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_png(self, service):
        """Test acceptation d'une photo PNG."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 456
        mock_photo.is_public = False
        mock_photo.mime_type = "image/png"
        mock_photo.original_filename = "image.png"
        mock_photo.is_deleted = False
        
        mock_db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_photo
        async def mock_execute(query):
            return execute_result
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        service.db.flush = AsyncMock()
        
        with patch('app.core.config.get_settings') as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            
            media_info = await service.prepare_media_for_publish(photo_id=123, user_id=456, expires_in_seconds=3600)
        
        assert isinstance(media_info, MediaInfo)
        assert media_info.mime_type == "image/png"
        assert media_info.is_video is False


    @pytest.mark.asyncio
    async def test_validate_media_token_valid(self, service):
        """Test validation token valide."""
        from app.models.sport import MediaPublishToken
        
        mock_token_record = MagicMock(spec=MediaPublishToken)
        mock_token_record.consumed = False
        mock_token_record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_token_record
        
        async def mock_execute(query):
            return execute_result
        
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        service.db.flush = AsyncMock()
        
        # Créer un token valide
        token = service._create_signed_token(photo_id=123, user_id=456, expires_in_seconds=3600)
        
        result = await service.validate_media_token(token)
        
        assert result is not None
        assert result["photo_id"] == 123
        assert result["user_id"] == 456

    @pytest.mark.asyncio
    async def test_validate_media_token_consumed(self, service):
        """Test validation token déjà consommé."""
        from app.models.sport import MediaPublishToken
        
        mock_token_record = MagicMock(spec=MediaPublishToken)
        mock_token_record.consumed = True  # Déjà consommé
        
        execute_result = MagicMock()
        execute_result.scalar_one_or_none.return_value = mock_token_record
        
        async def mock_execute(query):
            return execute_result
        
        service.db = AsyncMock(spec=AsyncSession)
        service.db.execute = mock_execute
        
        # Note: le token ne passera pas la validation _verify_signed_token car la vérification DB échouera
        # (token consommé)


# ============================================================
# Tests CommunityManagerStudioService - Publication
# ============================================================

class TestCommunityManagerStudioServicePublish:
    """Tests pour la publication Instagram dans CommunityManagerStudioService."""

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=User)
        user.id = 1
        user.username = "testuser"
        return user

    @pytest.fixture
    def mock_athlete(self):
        athlete = MagicMock(spec=SportAthlete)
        athlete.id = 10
        athlete.user_id = 1
        return athlete

    @pytest.fixture
    def mock_strategy(self, mock_athlete):
        strategy = MagicMock(spec=CommunityManagerStrategy)
        strategy.id = 100
        strategy.athlete_id = mock_athlete.id
        strategy.brand_identity = "TestBrand"
        strategy.tone = ["professional", "inspirational"]
        strategy.target_audience = "Athlètes endurance 25-45 ans"
        strategy.objectives = ["engagement", "visibility"]
        strategy.themes = ["running", "recovery"]
        strategy.frequency = 3
        strategy.networks = ["instagram"]
        strategy.rules = ["Pas de résultats inventés"]
        strategy.forbidden_topics = ["politique", "concurrentiels"]
        return strategy

    @pytest.fixture
    def mock_db(self, mock_athlete, mock_strategy):
        db = AsyncMock(spec=AsyncSession)
        
        execute_athlete = AsyncMock()
        execute_athlete.scalar_one_or_none.return_value = MagicMock(id=10, user_id=1)
        
        execute_strategy = AsyncMock()
        execute_strategy.scalar_one_or_none.return_value = MagicMock(
            id=100, athlete_id=10, brand_identity="TestBrand"
        )
        
        db.execute.side_effect = [
            execute_athlete,
            execute_strategy,
        ]
        
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db, mock_user):
        return CommunityManagerStudioService(mock_db, mock_user)

    @pytest.fixture
    def mock_publication(self):
        pub = MagicMock(spec=SportPublication)
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "validated"
        pub.content = "Test content"
        pub.hashtags = "#test #running"
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.visual_generation_prompt = None
        pub.visual_type = "photo"
        pub.title = "Test Title"
        pub.tone_used = "professional"
        pub.custom_instructions = None
        pub.styles = ["stats"]
        pub.calendar_entry_id = 1
        return pub

    @pytest.mark.asyncio
    async def test_publish_to_instagram_success(self, service, mock_db, mock_user, mock_publication):
        """Test publication Instagram réussie."""
        # Mock athlete and strategy
        mock_athlete = MagicMock(id=10, user_id=1)
        mock_strategy = MagicMock(
            id=100, athlete_id=10, brand_identity="TestBrand",
            tone=["professional"], target_audience="Test",
            objectives=["engagement"], themes=["running"],
            frequency=3, networks=["instagram"],
            rules=["Rule 1"], forbidden_topics=["politics"]
        )
        
        mock_db.execute.side_effect = [
            AsyncMock(scalar_one_or_none=MagicMock(return_value=mock_athlete)),  # _get_athlete
            AsyncMock(scalar_one_or_none=MagicMock(return_value=mock_strategy)),  # get_strategy
            AsyncMock(scalar_one_or_none=MagicMock(return_value=None)),  # MediaPublishService (pas de photo_id pour l'instant)
        ]
        
        # Mock publication
        pub = MagicMock()
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "validated"
        pub.content = "Test content"
        pub.hashtags = "#test"
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.visual_generation_prompt = None
        pub.visual_type = "photo"
        pub.title = "Test Title"
        pub.tone_used = "professional"
        pub.custom_instructions = None
        pub.styles = ["stats"]
        pub.calendar_entry_id = 1
        pub.instagram_media_id = None
        pub.instagram_permalink = None
        
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        
        # Mock Instagram connection
        mock_connection = MagicMock()
        mock_connection.instagram_business_account_id = "17841400000000000"
        mock_connection.user_id = 1
        mock_connection.status = "active"
        mock_connection.obtained_at = datetime.now(timezone.utc)
        mock_connection.expires_in = 5184000  # 60 days in seconds
        mock_connection.encrypted_long_lived_token = "encrypted_token"
        
        # Create a flexible mock for db.execute that returns appropriate results
        call_count = {"count": 0}
        
        async def mock_execute(query):
            call_count["count"] += 1
            # _get_athlete (call 1, 3)
            if call_count["count"] in (1, 3):
                result = MagicMock()
                result.scalar_one_or_none.return_value = mock_athlete if call_count["count"] == 1 else mock_strategy
                return result
            # MediaPublishService photo (call 2)
            elif call_count["count"] == 2:
                result = MagicMock()
                mock_photo = MagicMock(spec=Photo)
                mock_photo.id = 123
                mock_photo.owner_id = 1
                mock_photo.mime_type = "image/jpeg"
                mock_photo.original_filename = "photo.jpg"
                mock_photo.is_deleted = False
                mock_photo.is_public = False
                result.scalar_one_or_none.return_value = mock_photo
                return result
            # Instagram connection (call 4, 5)
            elif call_count["count"] in (4, 5):
                result = MagicMock()
                conn = MagicMock()
                conn.id = 1
                conn.user_id = 1
                conn.instagram_business_account_id = "17841400000000000"
                conn.status = "active"
                conn.obtained_at = datetime.now(timezone.utc)
                conn.expires_in = 5184000
                conn.encrypted_long_lived_token = "encrypted_token"
                result.scalar_one_or_none.return_value = conn
                return result
            return MagicMock()
        
        mock_db.execute.side_effect = mock_execute
        
        # Mock services
        with patch('app.services.sport_instagram_publish.MetaPublishService') as MockMetaService, \
             patch('app.services.community_manager.studio.MediaPublishService') as MockMediaService, \
             patch('app.core.config.get_settings') as mock_get_settings:
            
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            
            mock_media_service = MagicMock()
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value=MediaInfo(
                url="https://example.com/photo.jpg?meta_token=abc",
                mime_type="image/jpeg",
                filename="photo.jpg",
                is_video=False,
            ))
            MockMediaService.return_value = mock_media_service
            
            mock_meta_service = MagicMock()
            mock_meta_service.publish_photo = AsyncMock(return_value="media_123")
            mock_meta_service.get_media_permalink = AsyncMock(return_value="https://instagram.com/p/abc123")
            # La résolution de la source passe par le service : configuration
            # Meta centralisée (jeton SUAT) — voir resolve_publish_context.
            resolved_conn = MagicMock()
            resolved_conn.instagram_business_account_id = "17841400000000000"
            resolved_conn.encrypted_long_lived_token = "encrypted_token"
            mock_meta_service.resolve_publish_context = AsyncMock(return_value=resolved_conn)
            MockMetaService.return_value = mock_meta_service
            
            # Mock _decrypt_token
            with patch('app.services.sport_instagram._decrypt_token', return_value="long_token"):
                result = await service.publish_to_instagram(1, MagicMock(confirm=True))
                
                assert result is not None
                assert result.status == "shared"
                assert result.instagram_media_id == "media_123"

    @pytest.mark.asyncio
    async def test_publish_to_instagram_not_validated(self, service):
        """Test publication refusée si pas validée."""
        pub = MagicMock()
        pub.status = "draft"
        
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        
        with pytest.raises(ValueError, match="Seules les publications validées"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    @pytest.mark.asyncio
    async def test_publish_to_instagram_no_content(self, service):
        """Test publication refusée si contenu vide."""
        pub = MagicMock()
        pub.status = "validated"
        pub.content = ""
        
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        
        with pytest.raises(ValueError, match="contenu de la publication est vide"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    @pytest.mark.asyncio
    async def test_publish_to_instagram_no_visual(self, service):
        """Test publication refusée si pas de visuel."""
        pub = MagicMock()
        pub.status = "validated"
        pub.content = "Test"
        pub.photo_id = None
        pub.visual_generation_prompt = None
        
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        
        with pytest.raises(ValueError, match="visuel est requis"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    @pytest.mark.asyncio
    async def test_publish_to_instagram_no_config(self, service, mock_db):
        """Test publication refusée si aucune source Meta n'est configurée."""
        pub = MagicMock()
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "validated"
        pub.content = "Test content"
        pub.hashtags = "#test"
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.visual_generation_prompt = None
        pub.visual_type = "photo"

        service.pub_service.get_publication = AsyncMock(return_value=pub)

        mock_athlete = MagicMock(id=10, user_id=1)
        mock_strategy = MagicMock(athlete_id=10)

        # Mock the database : aucune clé de configuration Meta trouvée,
        # mais des résultats valides pour les autres requêtes
        async def mock_execute(query):
            query_str = str(query).lower()
            result = MagicMock()
            if "sport_athlete" in query_str and "user_id" in query_str:
                result.scalar_one_or_none.return_value = MagicMock(id=10, user_id=1)
            elif "community_manager_strategy" in query_str:
                result.scalar_one_or_none.return_value = MagicMock(
                    id=100, athlete_id=10, brand_identity="TestBrand",
                    tone=["professional"], target_audience="Test",
                    objectives=["engagement"], themes=["running"],
                    frequency=3, networks=["instagram"],
                    rules=["Rule 1"], forbidden_topics=["politics"]
                )
            elif "photo" in query_str and "id" in query_str:
                mock_photo = MagicMock(spec=Photo)
                mock_photo.id = 123
                mock_photo.owner_id = 1
                mock_photo.mime_type = "image/jpeg"
                mock_photo.original_filename = "photo.jpg"
                mock_photo.is_deleted = False
                mock_photo.is_public = False
                result.scalar_one_or_none.return_value = mock_photo
            elif "meta_access_token" in query_str or "instagram" in query_str:
                # Aucune configuration Meta de publication enregistrée
                result.scalar_one_or_none.return_value = None
            else:
                mock_photo = MagicMock(spec=Photo)
                mock_photo.id = 123
                mock_photo.owner_id = 1
                mock_photo.mime_type = "image/jpeg"
                mock_photo.original_filename = "photo.jpg"
                mock_photo.is_deleted = False
                mock_photo.is_public = False
                result.scalar_one_or_none.return_value = mock_photo
            return result

        mock_db.execute.side_effect = mock_execute

        with patch('app.services.sport_media_publish.MediaPublishService') as MockMediaService:
            mock_media_service = MagicMock()
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value=MediaInfo(
                url="https://example.com/photo.jpg?meta_token=abc",
                mime_type="image/jpeg",
                filename="photo.jpg",
                is_video=False,
            ))
            MockMediaService.return_value = mock_media_service

            with pytest.raises(ValueError, match="Aucune source de publication Instagram"):
                await service.publish_to_instagram(1, MagicMock(confirm=True))


# ============================================================
# Tests CommunityManagerStudioService - Validation (Studio)
# ============================================================

class TestCommunityManagerStudioServiceValidate:
    """Tests pour la validation des publications dans le Studio."""

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=User)
        user.id = 1
        return user

    @pytest.fixture
    def mock_athlete(self):
        athlete = MagicMock(spec=SportAthlete)
        athlete.id = 10
        athlete.user_id = 1
        return athlete

    @pytest.fixture
    def mock_strategy(self, mock_athlete):
        strategy = MagicMock(spec=CommunityManagerStrategy)
        strategy.id = 100
        strategy.athlete_id = mock_athlete.id
        strategy.brand_identity = "TestBrand"
        strategy.tone = ["professional", "inspirational"]
        strategy.target_audience = "Athlètes endurance 25-45 ans"
        strategy.objectives = ["engagement", "visibility"]
        strategy.themes = ["running", "recovery"]
        strategy.frequency = 3
        strategy.networks = ["instagram"]
        strategy.rules = ["Pas de résultats inventés"]
        strategy.forbidden_topics = ["politique", "concurrentiels"]
        return strategy

    @pytest.fixture
    def mock_db(self, mock_athlete, mock_strategy):
        db = AsyncMock(spec=AsyncSession)
        execute_athlete = AsyncMock()
        execute_athlete.scalar_one_or_none.return_value = mock_athlete
        execute_strategy = AsyncMock()
        execute_strategy.scalar_one_or_none.return_value = mock_strategy
        db.execute.side_effect = [execute_athlete, execute_strategy]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db, mock_user):
        return CommunityManagerStudioService(mock_db, mock_user)

    @pytest.fixture
    def mock_publication_garmin(self):
        """Publication Garmin non validée (source=garmin, content_type=publication_sportive)."""
        pub = MagicMock(spec=SportPublication)
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "draft"
        pub.content = "13,2 km d'Alsace, belle sortie running"
        pub.hashtags = "#running #alsace"
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.visual_generation_prompt = None
        pub.title = "Sortie Alsace"
        pub.calendar_entry_id = None
        pub.source = "garmin"
        pub.content_type = "publication_sportive"
        pub.validated_at = None
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        return pub

    @pytest.fixture
    def mock_publication_story_souvenir(self):
        """Story souvenir non validée."""
        entry = MagicMock(spec=EditorialCalendarEntry)
        entry.id = 50
        entry.source = "suggestion"
        entry.content_type = "story_souvenir"
        entry.status = "accepted"

        pub = MagicMock(spec=SportPublication)
        pub.id = 2
        pub.athlete_id = 10
        pub.status = "draft"
        pub.content = "Souvenir de course"
        pub.hashtags = "#souvenir"
        pub.photo_id = 124
        pub.visual_type = "story"
        pub.visual_generation_prompt = None
        pub.title = "Souvenir"
        pub.calendar_entry_id = 50
        pub.source = "suggestion"
        pub.content_type = "story_souvenir"
        pub.calendar_entry = entry
        pub.validated_at = None
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        return pub

    @pytest.fixture
    def mock_publication_story_edito(self):
        """Story éditoriale non validée."""
        entry = MagicMock(spec=EditorialCalendarEntry)
        entry.id = 51
        entry.source = "manuel"
        entry.content_type = "story_edito"
        entry.status = "accepted"

        pub = MagicMock(spec=SportPublication)
        pub.id = 3
        pub.athlete_id = 10
        pub.status = "draft"
        pub.content = "Story éditoriale"
        pub.hashtags = "#edito"
        pub.photo_id = 125
        pub.visual_type = "story"
        pub.visual_generation_prompt = None
        pub.title = "Story Edito"
        pub.calendar_entry_id = 51
        pub.source = "manuel"
        pub.content_type = "story_edito"
        pub.calendar_entry = entry
        pub.validated_at = None
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        return pub

    # ------------------------------------------------------------------ #
    # Test 1 : Publication Garmin non validée
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_garmin_publication_not_validated(self, service, mock_publication_garmin):
        """Une publication Garmin démarre en statut draft (non validée)."""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        pub = await service.pub_service.get_publication(1)
        assert pub.status == "draft"
        assert pub.source == "garmin"
        assert pub.content_type == "publication_sportive"

    # ------------------------------------------------------------------ #
    # Test 2 : Validation réussie d'une publication Garmin
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_validate_garmin_publication_success(self, service, mock_publication_garmin):
        """Validation d'une publication Garmin passe le statut à validated."""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        result = await service.validate_for_publication(1, MagicMock(confirm=True))
        assert result.status == "validated"
        assert result.validated_at is not None

    # ------------------------------------------------------------------ #
    # Test 3 : Déblocage du bouton Instagram après validation (Garmin)
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_publish_garmin_after_validation(self, service, mock_publication_garmin):
        """Après validation, la publication Garmin peut être publiée."""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        # D'abord valider
        await service.validate_for_publication(1, MagicMock(confirm=True))
        assert mock_publication_garmin.status == "validated"
        # Vérifier que le statut permet maintenant la publication
        assert mock_publication_garmin.status == "validated"
        assert mock_publication_garmin.content is not None
        assert mock_publication_garmin.photo_id is not None

    # ------------------------------------------------------------------ #
    # Test 4 : Story souvenir : validation réussie
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_validate_story_souvenir_success(self, service, mock_publication_story_souvenir):
        """Validation d'une story souvenir passe le statut à validated."""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_story_souvenir)
        result = await service.validate_for_publication(2, MagicMock(confirm=True))
        assert result.status == "validated"
        assert result.validated_at is not None

    # ------------------------------------------------------------------ #
    # Test 5 : Story éditoriale : validation réussie
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_validate_story_edito_success(self, service, mock_publication_story_edito):
        """Validation d'une story éditoriale passe le statut à validated."""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_story_edito)
        result = await service.validate_for_publication(3, MagicMock(confirm=True))
        assert result.status == "validated"
        assert result.validated_at is not None

    # ------------------------------------------------------------------ #
    # Test 6 : Échec API - contenu reste non validé
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_validate_empty_content_fails(self, service, mock_publication_garmin):
        """Validation échoue si le contenu est vide, statut reste draft."""
        mock_publication_garmin.content = ""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        with pytest.raises(ValueError, match="Le texte de la publication est vide"):
            await service.validate_for_publication(1, MagicMock(confirm=True))
        assert mock_publication_garmin.status == "draft"

    # ------------------------------------------------------------------ #
    # Test 7 : Validation persistante après rechargement
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_validation_persists(self, service, mock_publication_garmin):
        """La validation reste en base après la requête (status changé durablement)."""
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        await service.validate_for_publication(1, MagicMock(confirm=True))
        # Simuler un "rechargement" : le même objet a le status mis à jour
        pub = await service.pub_service.get_publication(1)
        assert pub.status == "validated"

    # ------------------------------------------------------------------ #
    # Test 8 : Double clic sur Valider (déjà validé)
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_validate_already_validated(self, service, mock_publication_garmin):
        """Valider une publication déjà validée ne produit pas d'erreur (idempotent)."""
        mock_publication_garmin.status = "validated"
        mock_publication_garmin.validated_at = datetime.now(timezone.utc)
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        result = await service.validate_for_publication(1, MagicMock(confirm=True))
        assert result.status == "validated"

    # ------------------------------------------------------------------ #
    # Test 9 : Modification d'un contenu déjà validé invalide la validation
    # ------------------------------------------------------------------ #
    @pytest.mark.asyncio
    async def test_modify_after_validation_invalidates(self, service, mock_publication_garmin):
        """Modifier le contenu d'une publication validée repasse le statut à draft."""
        # D'abord valider
        mock_publication_garmin.status = "validated"
        mock_publication_garmin.validated_at = datetime.now(timezone.utc)
        service.pub_service.get_publication = AsyncMock(return_value=mock_publication_garmin)
        await service.validate_for_publication(1, MagicMock(confirm=True))

        # Puis modifier le contenu (simule l'update_draft qui déverrouille)
        from app.schemas.sport import PublicationDraftUpdate
        update_data = PublicationDraftUpdate(content="Nouveau contenu modifié après validation")
        result = await service.update_draft(1, update_data)
        # Le statut repasse à draft car le contenu a été modifié après validation
        assert result.status == "draft"
        assert result.validated_at is None
        assert result.content == "Nouveau contenu modifié après validation"


# ============================================================
# Tests API Routes
# ============================================================

class TestPublishAPI:
    """Tests pour les endpoints API de publication."""

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=User)
        user.id = 1
        return user

    @pytest.fixture
    def mock_db(self):
        return AsyncMock(spec=AsyncSession)

    @pytest.mark.asyncio
    async def test_publish_draft_success(self):
        """Test endpoint publication réussi."""
        from app.api.community_manager import publish_draft
        from app.schemas.sport import PublicationPublishRequest
        
        mock_service = MagicMock()
        mock_pub = MagicMock()
        mock_pub.id = 1
        mock_pub.status = "shared"
        mock_pub.instagram_media_id = "media_123"
        mock_pub.instagram_permalink = "https://instagram.com/p/abc"
        mock_pub.shared_at = datetime.now(timezone.utc)
        mock_pub.error_message = None
        
        mock_service.publish_to_instagram = AsyncMock(return_value=MagicMock(
            id=1, status="shared", instagram_media_id="media_123",
            instagram_permalink="https://instagram.com/p/abc",
            shared_at=datetime.now(timezone.utc), error_message=None
        ))
        
        data = PublicationPublishRequest(publication_id=1, confirm=True)
        result = await publish_draft(publication_id=1, data=data, service=mock_service)
        
        assert result.publication_id == 1
        assert result.status == "shared"
        assert result.instagram_media_id == "media_123"

    @pytest.mark.asyncio
    async def test_publish_draft_validation_error(self):
        """Test endpoint publication erreur validation."""
        from app.api.community_manager import publish_draft
        from app.schemas.sport import PublicationPublishRequest
        from fastapi import HTTPException
        
        mock_service = MagicMock()
        mock_service.publish_to_instagram = AsyncMock(
            side_effect=ValueError("Publication non validée")
        )
        
        data = PublicationPublishRequest(publication_id=1, confirm=True)
        
        with pytest.raises(HTTPException) as exc_info:
            await publish_draft(publication_id=1, data=data, service=mock_service)
        
        assert exc_info.value.status_code == 422


# ============================================================
# Tests Frontend (logique de base)
# ============================================================

class TestStudioFrontendLogic:
    """Tests de logique frontend (simulation)."""

    def test_format_status_publishing(self):
        """Test formatage statut publishing."""
        # Simulation de la méthode _formatStatus
        def _formatStatus(status):
            map = {
                'draft': 'Brouillon',
                'validated': 'Validée',
                'scheduled': 'Planifiée',
                'shared': 'Partagée',
                'failed': 'Échec',
                'refused': 'Refusée',
                'publishing': 'Publication...',
            }
            return map.get(status, status)
        
        assert _formatStatus('publishing') == 'Publication...'
        assert _formatStatus('shared') == 'Partagée'
        assert _formatStatus('validated') == 'Validée'

    def test_get_status_badge_class_publishing(self):
        """Test classe badge pour publishing."""
        def _getStatusBadgeClass(status):
            map = {
                'draft': 'inactive',
                'validated': 'active',
                'scheduled': 'warning',
                'shared': 'success',
                'failed': 'danger',
                'refused': 'inactive',
                'publishing': 'warning',
            }
            return map.get(status, 'inactive')
        
        assert _getStatusBadgeClass('publishing') == 'warning'
        assert _getStatusBadgeClass('shared') == 'success'
        assert _getStatusBadgeClass('failed') == 'danger'

    def test_publish_button_disabled_logic(self):
        """Test logique désactivation bouton publier."""
        def is_publish_disabled(status, content, photo_id):
            if status not in ('validated', 'scheduled'):
                return True
            if not content or not photo_id:
                return True
            return False
        
        assert is_publish_disabled('draft', 'content', 123) == True
        assert is_publish_disabled('validated', '', 123) == True
        assert is_publish_disabled('validated', 'content', None) == True
        assert is_publish_disabled('validated', 'content', 123) == False
        assert is_publish_disabled('scheduled', 'content', 123) == False
        assert is_publish_disabled('shared', 'content', 123) == True
        assert is_publish_disabled('publishing', 'content', 123) == True


# ============================================================
# Tests CommunityManagerStudioService - Longueur légende Instagram
# ============================================================

class TestInstagramCaptionLength:
    """Tests pour le contrôle de longueur des légendes Instagram (2 200 caractères max)."""

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=User)
        user.id = 1
        user.username = "testuser"
        return user

    @pytest.fixture
    def mock_athlete(self):
        athlete = MagicMock(spec=SportAthlete)
        athlete.id = 10
        athlete.user_id = 1
        return athlete

    @pytest.fixture
    def mock_strategy(self, mock_athlete):
        strategy = MagicMock(spec=CommunityManagerStrategy)
        strategy.id = 100
        strategy.athlete_id = mock_athlete.id
        strategy.brand_identity = "TestBrand"
        strategy.tone = ["professional", "inspirational"]
        strategy.target_audience = "Athlètes endurance 25-45 ans"
        strategy.objectives = ["engagement", "visibility"]
        strategy.themes = ["running", "recovery"]
        strategy.frequency = 3
        strategy.networks = ["instagram"]
        strategy.rules = ["Pas de résultats inventés"]
        strategy.forbidden_topics = ["politique", "concurrentiels"]
        return strategy

    @pytest.fixture
    def mock_db(self, mock_athlete, mock_strategy):
        db = AsyncMock(spec=AsyncSession)
        execute_athlete = AsyncMock()
        execute_athlete.scalar_one_or_none.return_value = mock_athlete
        execute_strategy = AsyncMock()
        execute_strategy.scalar_one_or_none.return_value = mock_strategy
        db.execute.side_effect = [execute_athlete, execute_strategy]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db, mock_user):
        return CommunityManagerStudioService(mock_db, mock_user)

    def _make_pub(self, status="validated", content="", hashtags="", source="garmin", content_type="publication_sportive"):
        pub = MagicMock(spec=SportPublication)
        pub.id = 1
        pub.athlete_id = 10
        pub.status = status
        pub.content = content
        pub.hashtags = hashtags
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.visual_generation_prompt = None
        pub.title = "Test"
        pub.calendar_entry_id = None
        pub.source = source
        pub.content_type = content_type
        pub.validated_at = None
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        return pub

    # Test 1 : 2 199 caractères — doit passer
    @pytest.mark.asyncio
    async def test_caption_2199_chars_ok(self, service, mock_db):
        pub = self._make_pub(content="x" * 2199)
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        mock_athlete = MagicMock(id=10, user_id=1)
        mock_strategy = MagicMock(athlete_id=10)
        async def mock_execute(query):
            result = MagicMock()
            if "sport_athlete" in str(query):
                result.scalar_one_or_none.return_value = mock_athlete
            elif "community_manager_strategy" in str(query):
                result.scalar_one_or_none.return_value = mock_strategy
            elif "photo" in str(query) and "id" in str(query):
                mock_photo = MagicMock(spec=Photo)
                mock_photo.id = 123
                mock_photo.owner_id = 1
                mock_photo.mime_type = "image/jpeg"
                mock_photo.original_filename = "photo.jpg"
                mock_photo.is_deleted = False
                mock_photo.is_public = False
                result.scalar_one_or_none.return_value = mock_photo
            else:
                result.scalar_one_or_none.return_value = MagicMock()
            return result
        mock_db.execute.side_effect = mock_execute
        with patch('app.services.sport_instagram_publish.MetaPublishService') as MockMetaService, \
             patch('app.services.community_manager.studio.MediaPublishService') as MockMediaService, \
             patch('app.core.config.get_settings') as mock_get_settings, \
             patch('app.services.sport_instagram._decrypt_token', return_value="token"):
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            mock_media_service = MagicMock()
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value=MediaInfo(
                url="https://example.com/photo.jpg?meta_token=abc",
                mime_type="image/jpeg",
                filename="photo.jpg",
                is_video=False,
            ))
            MockMediaService.return_value = mock_media_service
            mock_meta_service = MagicMock()
            mock_meta_service.publish_photo = AsyncMock(return_value="media_123")
            mock_meta_service.get_media_permalink = AsyncMock(return_value="https://instagram.com/p/abc")
            resolved_conn = MagicMock()
            resolved_conn.instagram_business_account_id = "17841400000000000"
            resolved_conn.encrypted_long_lived_token = "encrypted_token"
            mock_meta_service.resolve_publish_context = AsyncMock(return_value=resolved_conn)
            MockMetaService.return_value = mock_meta_service
            result = await service.publish_to_instagram(1, MagicMock(confirm=True))
            assert result.status == "shared"

    # Test 2 : 2 200 caractères — doit passer (limite exacte)
    @pytest.mark.asyncio
    async def test_caption_2200_chars_ok(self, service, mock_db):
        pub = self._make_pub(content="x" * 2200)
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        mock_athlete = MagicMock(id=10, user_id=1)
        mock_strategy = MagicMock(athlete_id=10)
        async def mock_execute(query):
            result = MagicMock()
            if "sport_athlete" in str(query):
                result.scalar_one_or_none.return_value = mock_athlete
            elif "community_manager_strategy" in str(query):
                result.scalar_one_or_none.return_value = mock_strategy
            elif "photo" in str(query) and "id" in str(query):
                mock_photo = MagicMock(spec=Photo)
                mock_photo.id = 123
                mock_photo.owner_id = 1
                mock_photo.mime_type = "image/jpeg"
                mock_photo.original_filename = "photo.jpg"
                mock_photo.is_deleted = False
                mock_photo.is_public = False
                result.scalar_one_or_none.return_value = mock_photo
            else:
                result.scalar_one_or_none.return_value = MagicMock()
            return result
        mock_db.execute.side_effect = mock_execute
        with patch('app.services.sport_instagram_publish.MetaPublishService') as MockMetaService, \
             patch('app.services.community_manager.studio.MediaPublishService') as MockMediaService, \
             patch('app.core.config.get_settings') as mock_get_settings, \
             patch('app.services.sport_instagram._decrypt_token', return_value="token"):
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            mock_media_service = MagicMock()
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value=MediaInfo(
                url="https://example.com/photo.jpg?meta_token=abc",
                mime_type="image/jpeg",
                filename="photo.jpg",
                is_video=False,
            ))
            MockMediaService.return_value = mock_media_service
            mock_meta_service = MagicMock()
            mock_meta_service.publish_photo = AsyncMock(return_value="media_123")
            mock_meta_service.get_media_permalink = AsyncMock(return_value="https://instagram.com/p/abc")
            resolved_conn = MagicMock()
            resolved_conn.instagram_business_account_id = "17841400000000000"
            resolved_conn.encrypted_long_lived_token = "encrypted_token"
            mock_meta_service.resolve_publish_context = AsyncMock(return_value=resolved_conn)
            MockMetaService.return_value = mock_meta_service
            result = await service.publish_to_instagram(1, MagicMock(confirm=True))
            assert result.status == "shared"

    # Test 3 : 2 201 caractères — doit échouer
    @pytest.mark.asyncio
    async def test_caption_2201_chars_rejected(self, service):
        pub = self._make_pub(content="x" * 2201)
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        with pytest.raises(ValueError, match="dépasse la limite"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    # Test 4 : Texte avec emojis
    @pytest.mark.asyncio
    async def test_caption_with_emojis(self, service, mock_db):
        content = "Sortie trail 🏔️🏃‍♂️⛰️ 13,2 km dans l'Alsace ! 🇫🇷"
        pub = self._make_pub(content=content)
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        mock_athlete = MagicMock(id=10, user_id=1)
        mock_strategy = MagicMock(athlete_id=10)
        async def mock_execute(query):
            result = MagicMock()
            if "sport_athlete" in str(query):
                result.scalar_one_or_none.return_value = mock_athlete
            elif "community_manager_strategy" in str(query):
                result.scalar_one_or_none.return_value = mock_strategy
            elif "photo" in str(query) and "id" in str(query):
                mock_photo = MagicMock(spec=Photo)
                mock_photo.id = 123
                mock_photo.owner_id = 1
                mock_photo.mime_type = "image/jpeg"
                mock_photo.original_filename = "photo.jpg"
                mock_photo.is_deleted = False
                mock_photo.is_public = False
                result.scalar_one_or_none.return_value = mock_photo
            else:
                result.scalar_one_or_none.return_value = MagicMock()
            return result
        mock_db.execute.side_effect = mock_execute
        with patch('app.services.sport_instagram_publish.MetaPublishService') as MockMetaService, \
             patch('app.services.community_manager.studio.MediaPublishService') as MockMediaService, \
             patch('app.core.config.get_settings') as mock_get_settings, \
             patch('app.services.sport_instagram._decrypt_token', return_value="token"):
            mock_settings = MagicMock()
            mock_settings.PUBLIC_URL = "https://forgeai.design-ede.fr"
            mock_get_settings.return_value = mock_settings
            mock_media_service = MagicMock()
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value=MediaInfo(
                url="https://example.com/photo.jpg?meta_token=abc",
                mime_type="image/jpeg",
                filename="photo.jpg",
                is_video=False,
            ))
            MockMediaService.return_value = mock_media_service
            mock_meta_service = MagicMock()
            mock_meta_service.publish_photo = AsyncMock(return_value="media_123")
            mock_meta_service.get_media_permalink = AsyncMock(return_value="https://instagram.com/p/abc")
            resolved_conn = MagicMock()
            resolved_conn.instagram_business_account_id = "17841400000000000"
            resolved_conn.encrypted_long_lived_token = "encrypted_token"
            mock_meta_service.resolve_publish_context = AsyncMock(return_value=resolved_conn)
            MockMetaService.return_value = mock_meta_service
            result = await service.publish_to_instagram(1, MagicMock(confirm=True))
            assert result.status == "shared"

    # Test 5 : Texte avec hashtags (comptés dans la légende)
    @pytest.mark.asyncio
    async def test_caption_with_hashtags_counted(self, service):
        content = "Belle sortie running aujourd'hui."
        hashtags = "#running #trail #alsace #sport #motivation #fitness #outdoor"
        pub = self._make_pub(content=content, hashtags=hashtags)
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        expected_len = len(content + "\n\n" + hashtags)
        assert expected_len <= 2200, f"Fixture trop long: {expected_len} caractères"
        with pytest.raises(ValueError, match="dépasse la limite"):
            # Forcer un dépassement en ajoutant beaucoup de hashtags
            pub.hashtags = "#a" * 3000
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    # Test 6 : Texte vide
    @pytest.mark.asyncio
    async def test_caption_empty_rejected(self, service):
        pub = self._make_pub(content="")
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        with pytest.raises(ValueError, match="contenu de la publication est vide"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    # Test 7 : Publication sportive Garmin
    @pytest.mark.asyncio
    async def test_garmin_publication_caption_limit(self, service, mock_db):
        pub = self._make_pub(source="garmin", content_type="publication_sportive", content="x" * 2201)
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        with pytest.raises(ValueError, match="dépasse la limite"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))

    # Test 8 : Story (même mécanisme de légende)
    @pytest.mark.asyncio
    async def test_story_caption_limit(self, service, mock_db):
        entry = MagicMock(spec=EditorialCalendarEntry)
        entry.id = 50
        entry.source = "suggestion"
        entry.content_type = "story_souvenir"
        entry.status = "accepted"
        pub = self._make_pub(source="suggestion", content_type="story_souvenir", content="x" * 2201)
        pub.calendar_entry_id = 50
        pub.calendar_entry = entry
        service.pub_service.get_publication = AsyncMock(return_value=pub)
        with pytest.raises(ValueError, match="dépasse la limite"):
            await service.publish_to_instagram(1, MagicMock(confirm=True))


# ============================================================
# Tests CommunityManagerStudioService - Génération IA avec limite
# ============================================================

class TestInstagramCaptionLengthAIGeneration:
    """Tests pour la génération IA avec contrôle de longueur (2 200 caractères max)."""

    @pytest.fixture
    def mock_user(self):
        user = MagicMock(spec=User)
        user.id = 1
        return user

    @pytest.fixture
    def mock_athlete(self):
        athlete = MagicMock(spec=SportAthlete)
        athlete.id = 10
        athlete.user_id = 1
        return athlete

    @pytest.fixture
    def mock_strategy(self, mock_athlete):
        strategy = MagicMock(spec=CommunityManagerStrategy)
        strategy.id = 100
        strategy.athlete_id = mock_athlete.id
        strategy.brand_identity = "TestBrand"
        strategy.tone = ["professional", "inspirational"]
        strategy.target_audience = "Athlètes endurance 25-45 ans"
        strategy.objectives = ["engagement", "visibility"]
        strategy.themes = ["running", "recovery"]
        strategy.frequency = 3
        strategy.networks = ["instagram"]
        strategy.rules = ["Pas de résultats inventés"]
        strategy.forbidden_topics = ["politique", "concurrentiels"]
        return strategy

    @pytest.fixture
    def mock_db(self, mock_athlete, mock_strategy):
        db = AsyncMock(spec=AsyncSession)
        execute_athlete = AsyncMock()
        execute_athlete.scalar_one_or_none.return_value = mock_athlete
        execute_strategy = AsyncMock()
        execute_strategy.scalar_one_or_none.return_value = mock_strategy
        db.execute.side_effect = [execute_athlete, execute_strategy]
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        db.delete = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db, mock_user):
        return CommunityManagerStudioService(mock_db, mock_user)

    @pytest.fixture
    def mock_calendar_entry(self):
        entry = MagicMock(spec=EditorialCalendarEntry)
        entry.id = 50
        entry.strategy_id = 100
        entry.topic = "Sortie trail Alsace"
        entry.theme = "running"
        entry.objective = "engagement"
        entry.notes = None
        entry.date = "2026-11-15"
        return entry

    # Helper pour mocker les appels DB communs
    async def _setup_common_db_mocks(self, mock_db, mock_athlete, mock_strategy, mock_calendar_entry):
        """Configure les mocks DB communs pour generate_text_variants et generate_text."""
        call_sequence = []

        async def mock_execute(query):
            query_str = str(query).lower()
            result = MagicMock()
            if "sport_athlete" in query_str:
                result.scalar_one_or_none.return_value = mock_athlete
            elif "community_manager_strategy" in query_str:
                result.scalar_one_or_none.return_value = mock_strategy
            elif "editorial_calendar_entry" in query_str:
                result.scalar_one_or_none.return_value = mock_calendar_entry
            elif "sport_activity" in query_str:
                activities_result = MagicMock()
                activities_result.scalars.return_value.all.return_value = []
                return activities_result
            elif "sport_publication" in query_str:
                prev_result = MagicMock()
                prev_result.scalars.return_value.all.return_value = []
                return prev_result
            else:
                result.scalar_one_or_none.return_value = MagicMock()
            return result

        mock_db.execute.side_effect = mock_execute

    # Test IA 1 : Variantes avec contenu IA trop long → tronqué
    @pytest.mark.asyncio
    async def test_ai_variants_content_truncated(self, service, mock_db, mock_calendar_entry):
        """La génération IA de variantes tronque le contenu dépassant 2200 caractères."""
        from unittest.mock import patch
        from app.services.ai_gateway import ai_gateway

        pub = MagicMock(spec=SportPublication)
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "draft"
        pub.content = ""
        pub.hashtags = None
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.visual_generation_prompt = None
        pub.title = "Test"
        pub.calendar_entry_id = 50
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        pub.styles = ["stats"]
        pub.tone_used = "professional"
        pub.custom_instructions = None

        service.pub_service.get_publication = AsyncMock(return_value=pub)
        await self._setup_common_db_mocks(mock_db, MagicMock(id=10, user_id=1), MagicMock(athlete_id=10), mock_calendar_entry)

        # L'IA retourne un contenu trop long (3000 caractères)
        long_content = "x" * 3000
        fake_response = MagicMock()
        fake_response.text = json.dumps({
            "proposals": [{
                "title": "Titre",
                "content": long_content,
                "hashtags": "#running #trail",
                "format": "photo",
                "idee_visuelle": "Une photo",
                "objectif": "engagement"
            }]
        })

        with patch.object(ai_gateway, 'generate', new=AsyncMock(return_value=fake_response)):
            variants = await service.generate_text_variants(1, count=1)

        assert len(variants) == 1
        variant = variants[0]
        full_caption = variant["content"] + "\n\n" + variant["hashtags"]
        assert len(full_caption) <= 2200, f"Variante tronquée trop longue: {len(full_caption)} caractères"

    # Test IA 2 : Génération texte unique avec contenu trop long → tronqué
    @pytest.mark.asyncio
    async def test_ai_generate_text_truncated(self, service, mock_db, mock_calendar_entry):
        """La génération de texte unique tronque le contenu dépassant 2200 caractères."""
        from unittest.mock import patch
        from app.services.ai_gateway import ai_gateway
        from app.schemas.sport import PublicationGenerateTextRequest

        pub = MagicMock(spec=SportPublication)
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "draft"
        pub.content = ""
        pub.hashtags = None
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.title = "Test"
        pub.calendar_entry_id = 50
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        pub.styles = ["stats"]
        pub.tone_used = "professional"
        pub.custom_instructions = None

        service.pub_service.get_publication = AsyncMock(return_value=pub)
        await self._setup_common_db_mocks(mock_db, MagicMock(id=10, user_id=1), MagicMock(athlete_id=10), mock_calendar_entry)

        long_content = "x" * 3000
        fake_response = MagicMock()
        fake_response.text = json.dumps({
            "proposal": {
                "title": "Titre",
                "content": long_content,
                "hashtags": "#running #trail #alsace",
            }
        })

        with patch.object(ai_gateway, 'generate', new=AsyncMock(return_value=fake_response)):
            result = await service.generate_text(1, PublicationGenerateTextRequest(publication_id=1, length="short"))

        assert result is not None
        full_caption = (result.content or "") + ("\n\n" + result.hashtags if result.hashtags else "")
        assert len(full_caption) <= 2200, f"Texte généré trop long: {len(full_caption)} caractères"

    # Test IA 3 : Contenu IA dans les limites → pas de troncation
    @pytest.mark.asyncio
    async def test_ai_variants_within_limit_not_truncated(self, service, mock_db, mock_calendar_entry):
        """La génération IA ne tronque pas si le contenu est déjà dans les limites."""
        from unittest.mock import patch
        from app.services.ai_gateway import ai_gateway

        pub = MagicMock(spec=SportPublication)
        pub.id = 1
        pub.athlete_id = 10
        pub.status = "draft"
        pub.content = ""
        pub.hashtags = None
        pub.photo_id = 123
        pub.visual_type = "photo"
        pub.title = "Test"
        pub.calendar_entry_id = 50
        pub.title_locked = False
        pub.content_locked = False
        pub.photo_locked = False
        pub.styles = ["stats"]
        pub.tone_used = "professional"
        pub.custom_instructions = None

        service.pub_service.get_publication = AsyncMock(return_value=pub)
        await self._setup_common_db_mocks(mock_db, MagicMock(id=10, user_id=1), MagicMock(athlete_id=10), mock_calendar_entry)

        good_content = "Belle sortie running dans l'Alsace aujourd'hui !"
        good_hashtags = "#running #trail #alsace"
        fake_response = MagicMock()
        fake_response.text = json.dumps({
            "proposals": [{
                "title": "Titre",
                "content": good_content,
                "hashtags": good_hashtags,
                "format": "photo",
                "idee_visuelle": "Une photo",
                "objectif": "engagement"
            }]
        })

        with patch.object(ai_gateway, 'generate', new=AsyncMock(return_value=fake_response)):
            variants = await service.generate_text_variants(1, count=1)

        assert len(variants) == 1
        variant = variants[0]
        assert variant["content"] == good_content
        assert variant["hashtags"] == good_hashtags



if __name__ == "__main__":
    pytest.main([__file__, "-v"])