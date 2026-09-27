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
async def test_goals_page_flow_list_create_and_analysis(client, admin_headers):
    from datetime import datetime, timedelta, timezone

    target_date = (datetime.now(timezone.utc).date() + timedelta(days=90)).isoformat()
    payload = {
        "name": "Trail d'automne",
        "goal_type": "distance",
        "target_value": 130.0,
        "unit": "km",
        "target_date": target_date,
    }
    created = await client.post("/sport/goals", json=payload, headers=admin_headers)
    assert created.status_code == 201

    listed = await client.get("/sport/goals", headers=admin_headers)
    assert listed.status_code == 200
    goal_id = created.json()["id"]
    assert any(item["id"] == goal_id for item in listed.json())

    analysis = await client.get("/sport/analysis/goals", headers=admin_headers)
    assert analysis.status_code == 200
    item = next(entry for entry in analysis.json() if entry["goal_id"] == goal_id)
    assert item["name"] == "Trail d'automne"
    assert item["days_remaining"] == 90
    assert item["target"]["value"] == 130.0
    assert "recent_28_days" in item


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
