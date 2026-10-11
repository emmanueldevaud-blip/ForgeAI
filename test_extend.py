import pytest
from datetime import date, timedelta

@pytest.mark.asyncio
async def test_extend_morning_to_full_removes_afternoon_in_other_room(client, admin_headers):
    """Morning in A, afternoon in B -> extend A to full should remove afternoon from B"""
    room_a, room_b = await _setup_bureau_rooms(client, admin_headers, names=("Bureau A", "Bureau B"))
    
    presence_date = _next_weekday(date.today()).isoformat()
    
    # Morning in A
    morning = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "morning"},
        headers=admin_headers,
    )
    assert morning.status_code == 200, morning.text
    assert morning.json()["period"] == "morning"
    
    # Afternoon in B
    afternoon = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_b, "is_present": True, "period": "afternoon"},
        headers=admin_headers,
    )
    assert afternoon.status_code == 200, afternoon.text
    assert afternoon.json()["period"] == "afternoon"
    
    # Check initial state
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "morning" for p in room_a_day["presences"])
    assert room_b_day["present_count"] == 1
    assert any(p["period"] == "afternoon" for p in room_b_day["presences"])
    
    # Extend room A to full
    full = await client.post(
        "/agenda/presences",
        json={"presence_date": presence_date, "room_id": room_a, "is_present": True, "period": "full"},
        headers=admin_headers,
    )
    print(f"Extend to full status: {full.status_code}, text: {full.text}")
    assert full.status_code == 200, full.text
    
    # Check final state
    planning = await client.get(f"/agenda/planning?view=week&anchor={presence_date}", headers=admin_headers)
    day = next(d for d in planning.json()["days"] if d["date"] == presence_date)
    room_a_day = next(r for r in day["rooms"] if r["room_id"] == room_a)
    room_b_day = next(r for r in day["rooms"] if r["room_id"] == room_b)
    
    print(f"Room A: {room_a_day}")
    print(f"Room B: {room_b_day}")
    
    # Room A should have full
    assert room_a_day["present_count"] == 1
    assert any(p["period"] == "full" for p in room_a_day["presences"])
    
    # Room B should have NO presences (afternoon removed)
    assert room_b_day["present_count"] == 0, f"Room B should be empty but has: {room_b_day['presences']}"

from tests.test_agenda import _setup_bureau_rooms, _next_weekday
