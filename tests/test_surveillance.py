from types import SimpleNamespace

import pytest

from app.services.surveillance import (
    decrypt_password,
    encrypt_password,
    test_camera_connection as check_camera_connection,
    validate_camera_target,
)


def test_camera_target_rejects_credentials_in_stream_url():
    with pytest.raises(ValueError, match="identifiants"):
        validate_camera_target("rtsp", None, None, "rtsp://user:password@camera.local/live")


def test_camera_target_accepts_local_http_host():
    validate_camera_target("http", "127.0.0.1", 8080, None)


def test_camera_password_is_encrypted_and_round_trips():
    encrypted = encrypt_password("secret-camera-password")
    assert encrypted != "secret-camera-password"
    assert decrypt_password(encrypted) == "secret-camera-password"


@pytest.mark.asyncio
async def test_unconfigured_remote_capture_is_not_reported_online():
    camera = SimpleNamespace(source_type="remote_agent", protocol=None, host=None, port=None, stream_url=None)
    online, message, status = await check_camera_connection(camera)
    assert online is False
    assert status == "unsupported"
    assert "agent" in message.lower()
