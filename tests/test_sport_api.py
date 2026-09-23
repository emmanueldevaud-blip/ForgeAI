import pytest


@pytest.mark.asyncio
async def test_sport_analysis_requires_permission(client, auth_headers):
    response = await client.get("/sport/athlete/profile", headers=auth_headers)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sport_dashboard_and_daily_analysis_are_available_to_admin(client, admin_headers):
    dashboard = await client.get("/sport/dashboard", headers=admin_headers)
    daily = await client.get("/sport/analysis/day", headers=admin_headers)
    goals = await client.get("/sport/analysis/goals", headers=admin_headers)

    assert dashboard.status_code == 200
    assert dashboard.json()["goal_analysis"] == []
    assert daily.status_code == 200
    assert goals.status_code == 200


@pytest.mark.asyncio
async def test_sport_coach_conversation_can_be_retrieved(client, admin_headers):
    response = await client.post("/sport/coach", headers=admin_headers, json={"question": "Quel est mon volume ?"})

    assert response.status_code == 200
    conversation_id = response.json()["conversation_id"]
    history = await client.get(f"/sport/coach/conversations/{conversation_id}", headers=admin_headers)

    assert history.status_code == 200
    assert [message["role"] for message in history.json()["messages"]] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_sport_conversation_cannot_be_accessed_with_another_athlete(client, admin_headers, db_session, auth_user):
    from app.services.sport import SportService

    conversation = await SportService(db_session, auth_user).coach("Question privée")
    response = await client.get(f"/sport/coach/conversations/{conversation['conversation_id']}", headers=admin_headers)

    assert response.status_code == 404
