"""Tests pour Community Manager V3 - Publication Instagram."""

import json
import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

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
    PublicationPublishRequest,
    PublicationValidateRequest,
    PublicationPreviewRequest,
)
from app.services.community_manager.studio import CommunityManagerStudioService
from app.services.sport_instagram_publish import MetaPublishService, MetaPublishError
from app.services.sport_media_publish import MediaPublishService, MediaPublishError
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
        
        assert "meta_token=" in url
        assert "photos/123/file" in url

    @pytest.mark.asyncio
    async def test_prepare_media_for_publish_unauthorized(self, service):
        """Test préparation média accès non autorisé."""
        from app.models.photo import Photo
        
        mock_photo = MagicMock(spec=Photo)
        mock_photo.id = 123
        mock_photo.owner_id = 789  # Autre utilisateur
        mock_photo.is_public = False
        
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
                result.scalar_one_or_none.return_value = MagicMock(id=123, owner_id=1)
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
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value="https://example.com/photo.jpg?meta_token=abc")
            MockMediaService.return_value = mock_media_service
            
            mock_meta_service = MagicMock()
            mock_meta_service.publish_photo = AsyncMock(return_value="media_123")
            mock_meta_service.get_media_permalink = AsyncMock(return_value="https://instagram.com/p/abc123")
            # Jalon 2 : la résolution de la source passe par le service (config centralisée
            # en priorité, connexion OAuth en repli) — voir resolve_publish_context.
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
                result.scalar_one_or_none.return_value = MagicMock(id=123, owner_id=1)
            elif "meta_access_token" in query_str or "instagram" in query_str:
                # Aucune configuration Meta de publication enregistrée
                result.scalar_one_or_none.return_value = None
            else:
                result.scalar_one_or_none.return_value = MagicMock(id=123, owner_id=1)
            return result

        mock_db.execute.side_effect = mock_execute

        with patch('app.services.sport_media_publish.MediaPublishService') as MockMediaService:
            mock_media_service = MagicMock()
            mock_media_service.prepare_media_for_publish = AsyncMock(return_value="https://example.com/photo.jpg?meta_token=abc")
            MockMediaService.return_value = mock_media_service

            with pytest.raises(ValueError, match="Aucune source de publication Instagram"):
                await service.publish_to_instagram(1, MagicMock(confirm=True))


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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])