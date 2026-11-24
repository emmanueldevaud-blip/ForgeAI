"""Tests ciblés du conteneur de publication Instagram Story."""

import httpx

from app.services.sport_instagram_publish import MetaPublishService, _MetaConfigContext


async def test_publish_story_uses_stories_media_type_without_caption(monkeypatch):
    container_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "story_media_1"}, request=request)
        if request.method == "POST" and request.url.path.endswith("/media"):
            container_requests.append(request)
            return httpx.Response(200, json={"id": "story_container_1"}, request=request)
        if request.method == "GET" and request.url.path.endswith("/story_container_1"):
            return httpx.Response(200, json={"status_code": "FINISHED"}, request=request)
        return httpx.Response(404, json={"error": {"message": "not_found"}}, request=request)

    real_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real_async_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr("app.services.sport_instagram_publish.httpx.AsyncClient", client_factory)
    service = MetaPublishService(None)

    async def get_token(_connection):
        return "test-token"

    monkeypatch.setattr(service, "_get_valid_token", get_token)
    context = _MetaConfigContext("unused", "17841400000000000")
    media_id = await service.publish_story(
        context,
        "https://cdn.example.com/story.jpg",
        mime_type="image/jpeg",
    )

    assert media_id == "story_media_1"
    assert len(container_requests) == 1
    params = container_requests[0].url.params
    assert params["media_type"] == "STORIES"
    assert params["image_url"] == "https://cdn.example.com/story.jpg"
    assert "caption" not in params
