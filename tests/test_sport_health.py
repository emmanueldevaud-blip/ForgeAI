"""Tests de la synchronisation et de l'API de santé Garmin."""

from datetime import date, timedelta

from sqlalchemy import select

from app.models.sport import SportHealthDaily
from app.services.garmin import SportGarminConnectService
from app.services.sport import SportService


class FakeGarminHealthClient:
    """Réponses simulées des méthodes santé de garminconnect 0.3.2."""

    def get_heart_rates(self, cdate):
        return {"maxHR": 150, "restingHR": 47}

    def get_rhr_day(self, cdate):
        return {"metricSummaries": [{"metricId": 60, "value": 46}]}

    def get_sleep_data(self, cdate):
        return {
            "dailySleepDTO": {
                "sleepTimeSeconds": 25200,
                "deepSleepSeconds": 4800,
                "lightSleepSeconds": 12000,
                "remSleepSeconds": 6000,
                "awakeTimeSeconds": 2400,
            },
            "sleepScore": 82,
        }

    def get_hrv_data(self, cdate):
        return {"hrv": 64, "status": "balanced"}

    def get_stress_data(self, cdate):
        return {"avgStressLevel": 28, "maxStressLevel": 71}

    def get_spo2_data(self, cdate):
        return {"averageSpO2": 96.5}

    def get_respiration_data(self, cdate):
        return {"avgWakingRespirationValue": 14.2}

    def get_training_readiness(self, cdate):
        return {"score": 71, "status": "productive"}

    def get_user_summary(self, cdate):
        return {"steps": 8432, "calories": 2450}

    def get_body_battery(self, startdate, enddate=None):
        start = date.fromisoformat(startdate)
        end = date.fromisoformat(enddate or startdate)
        items = []
        cursor = start
        while cursor <= end:
            items.append({"calendarDate": cursor.isoformat(), "bodyBatteryValuesArray": [40, 65, 82]})
            cursor += timedelta(days=1)
        return items

    def get_daily_steps(self, start, end):
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        items = []
        cursor = start_date
        while cursor <= end_date:
            items.append({"calendarDate": cursor.isoformat(), "steps": 8432})
            cursor += timedelta(days=1)
        return items


async def _athlete(db_session, user):
    return await SportService(db_session, user).get_or_create_athlete()


async def test_sync_health_stores_daily_payload(db_session, admin_user):
    athlete = await _athlete(db_session, admin_user)
    service = SportGarminConnectService(db_session)
    today = date.today()

    await service._sync_health(FakeGarminHealthClient(), athlete, today - timedelta(days=4))
    await db_session.commit()

    rows = (await db_session.execute(
        select(SportHealthDaily).where(SportHealthDaily.athlete_id == athlete.id)
    )).scalars().all()
    assert len(rows) == 5
    payload = sorted(rows, key=lambda row: row.day)[-1].health_json
    assert payload["sleep"]["sleepScore"] == 82
    assert payload["heart_rates"]["maxHR"] == 150
    assert payload["body_battery"]["bodyBatteryValuesArray"] == [40, 65, 82]
    assert payload["daily_summary"]["steps"] == 8432
    assert payload["daily_steps"]["steps"] == 8432


async def test_sync_health_skips_already_synced_days(db_session, admin_user):
    athlete = await _athlete(db_session, admin_user)
    service = SportGarminConnectService(db_session)
    today = date.today()
    old_day = today - timedelta(days=3)
    db_session.add(SportHealthDaily(
        athlete_id=athlete.id,
        day=old_day,
        source_type="garmin",
        health_json={"sleep": {"sleepScore": 60}},
    ))
    await db_session.commit()

    class CountingClient(FakeGarminHealthClient):
        sleep_calls = 0

        def get_sleep_data(self, cdate):
            CountingClient.sleep_calls += 1
            return super().get_sleep_data(cdate)

    client = CountingClient()
    await service._sync_health(client, athlete, today - timedelta(days=4))
    await db_session.commit()

    rows = (await db_session.execute(
        select(SportHealthDaily).where(SportHealthDaily.athlete_id == athlete.id)
    )).scalars().all()
    assert len(rows) == 5
    old_row = next(row for row in rows if row.day == old_day)
    assert old_row.health_json == {"sleep": {"sleepScore": 60}}
    # Les jours déjà synchronisés ne sont pas rappelés (sauf hier et aujourd'hui).
    assert client.sleep_calls == 4


async def test_health_endpoint_extracts_series(client, admin_headers, db_session, admin_user):
    athlete = await _athlete(db_session, admin_user)
    db_session.add(SportHealthDaily(
        athlete_id=athlete.id,
        day=date.today(),
        source_type="garmin",
        health_json={
            "sleep": {"dailySleepDTO": {"sleepTimeSeconds": 25200}, "sleepScore": 82},
            "heart_rates": {"maxHR": 150, "restingHR": 47},
            "hrv": {"hrv": 64, "status": "balanced"},
            "stress": {"avgStressLevel": 28},
            "daily_summary": {"steps": 8432, "calories": 2450},
        },
    ))
    await db_session.commit()

    response = await client.get("/sport/health?period=7", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["days_available"] == 1
    assert data["series"]["sleep"][0]["total_minutes"] == 420
    assert data["series"]["heart_rate"][0]["resting"] == 47
    assert data["series"]["hrv"][0]["status"] == "balanced"
    assert data["series"]["steps"][0]["steps"] == 8432
    assert data["summary"]["sleep_score_avg"] == 82
    assert data["summary"]["steps_avg"] == 8432
