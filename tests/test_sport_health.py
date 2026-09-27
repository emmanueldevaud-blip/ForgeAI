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

    await service._sync_health(FakeGarminHealthClient(), athlete)
    await db_session.commit()

    rows = (await db_session.execute(
        select(SportHealthDaily).where(SportHealthDaily.athlete_id == athlete.id)
    )).scalars().all()
    # La fenêtre santé couvre toujours les 31 derniers jours.
    assert len(rows) == 31
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
    await service._sync_health(client, athlete)
    await db_session.commit()

    rows = (await db_session.execute(
        select(SportHealthDaily).where(SportHealthDaily.athlete_id == athlete.id)
    )).scalars().all()
    assert len(rows) == 31
    old_row = next(row for row in rows if row.day == old_day)
    assert old_row.health_json == {"sleep": {"sleepScore": 60}}
    # Les jours déjà synchronisés ne sont pas rappelés (sauf hier et aujourd'hui).
    assert client.sleep_calls == 30


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


async def test_health_endpoint_extracts_real_garmin_shapes(client, admin_headers, db_session, admin_user):
    """Verrouille l'extraction sur les structures réellement retournées par garminconnect 0.3.2."""
    athlete = await _athlete(db_session, admin_user)
    day = date.today()
    db_session.add(SportHealthDaily(
        athlete_id=athlete.id,
        day=day,
        source_type="garmin",
        health_json={
            "heart_rates": {
                "restingHeartRate": 42, "maxHeartRate": 89, "minHeartRate": 40,
                "heartRateValues": [[1790377200000, 55], [1790377320000, 58]],
            },
            "sleep": {
                "dailySleepDTO": {
                    "sleepTimeSeconds": 31980, "deepSleepSeconds": 4320,
                    "lightSleepSeconds": 23880, "remSleepSeconds": 3780,
                    "awakeSleepSeconds": 2220, "avgHeartRate": 44.0,
                    "sleepScores": {"overall": {"value": 74, "qualifierKey": "FAIR"}},
                },
            },
            "hrv": {
                "hrvStatus": None,
                "hrvSummary": {"status": "BALANCED", "weeklyAvg": 55, "lastNightAvg": 38},
            },
            "body_battery": {"bodyBatteryValuesArray": [[1790377200000, 32], [1790433720000, 53]]},
            "daily_steps": {"totalSteps": 6904, "stepGoal": 15830},
            "daily_summary": {"totalSteps": 6904, "steps": None, "activeKilocalories": 249.0},
            "stress": {"avgStressLevel": 24, "maxStressLevel": 75},
            "readiness": [
                {"calendarDate": day.isoformat(), "score": 76, "level": "HIGH"},
                {"calendarDate": day.isoformat(), "score": 73, "level": "MODERATE"},
            ],
        },
    ))
    await db_session.commit()

    response = await client.get("/sport/health?period=7", headers=admin_headers)

    assert response.status_code == 200
    data = response.json()
    series = data["series"]
    assert series["heart_rate"][0]["resting"] == 42
    assert series["heart_rate"][0]["max"] == 89
    assert series["sleep"][0]["score"] == 74
    assert series["sleep"][0]["total_minutes"] == 533
    assert series["sleep"][0]["awake_minutes"] == 37
    assert series["hrv"][0]["value"] == 38
    assert series["hrv"][0]["status"] == "BALANCED"
    assert series["body_battery"][0]["min"] == 32
    assert series["body_battery"][0]["last"] == 53
    assert series["steps"][0]["steps"] == 6904
    assert series["steps"][0]["calories"] == 249
    assert series["readiness"][0]["score"] == 73
    assert series["readiness"][0]["status"] == "MODERATE"
    assert data["summary"]["sleep_score_avg"] == 74
    assert data["summary"]["steps_avg"] == 6904


async def test_recovery_context_for_ai(db_session, admin_user):
    service = SportService(db_session, admin_user)

    empty = await service.recovery_context()
    assert empty["available"] is False

    db_session.add(SportHealthDaily(
        athlete_id=(await _athlete(db_session, admin_user)).id,
        day=date.today(),
        source_type="garmin",
        health_json={
            "heart_rates": {"restingHeartRate": 42, "maxHeartRate": 89},
            "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 74}}, "sleepTimeSeconds": 31980}},
            "hrv": {"hrvSummary": {"status": "BALANCED", "lastNightAvg": 38}},
            "stress": {"avgStressLevel": 24},
            "body_battery": {"bodyBatteryValuesArray": [[1790377200000, 32], [1790433720000, 53]]},
            "readiness": [{"calendarDate": date.today().isoformat(), "score": 73, "level": "MODERATE"}],
        },
    ))
    await db_session.commit()

    ctx = await service.recovery_context()
    assert ctx["available"] is True
    assert ctx["latest"]["readiness_score"] == 73
    assert ctx["latest"]["sleep_score"] == 74
    assert ctx["latest"]["hrv_ms"] == 38
    assert ctx["latest"]["body_battery"] == 53
    assert ctx["period_averages"]["resting_hr"] == 42

    from app.services.sport_analysis import SportAnalysisEngine
    built = SportAnalysisEngine.build_context({}, [], {}, {}, [], recovery=ctx)
    assert built["recovery"]["available"] is True
    default = SportAnalysisEngine.build_context({}, [], {}, {}, [])
    assert default["recovery"]["available"] is False


async def test_coach_context_includes_all_health_data(db_session, admin_user):
    athlete = await _athlete(db_session, admin_user)
    db_session.add(SportHealthDaily(
        athlete_id=athlete.id,
        day=date.today(),
        source_type="garmin",
        health_json={
            "heart_rates": {"restingHeartRate": 42, "maxHeartRate": 89},
            "sleep": {"dailySleepDTO": {"sleepScores": {"overall": {"value": 74}}, "sleepTimeSeconds": 31980}},
            "readiness": [{"calendarDate": date.today().isoformat(), "score": 73, "level": "MODERATE"}],
        },
    ))
    await db_session.commit()

    service = SportService(db_session, admin_user)
    context = await service.build_coach_context(athlete)

    assert context["recovery"]["available"] is True
    health = context["health"]
    assert health["days_with_data"] == 1
    assert health["summary"]["sleep_score_avg"] == 74
    ssc_index = health["columns"].index("ssc")
    rhr_index = health["columns"].index("rhr")
    assert health["rows"][0][ssc_index] == 74
    assert health["rows"][0][rhr_index] == 42


def test_activity_detail_segments_and_curve():
    from types import SimpleNamespace
    from app.services.sport_analysis import SportAnalysisEngine

    descriptors = [
        {"key": "directTimestamp", "metricsIndex": 0},
        {"key": "sumDistance", "metricsIndex": 1},
        {"key": "directSpeed", "metricsIndex": 2},
        {"key": "directHeartRate", "metricsIndex": 3},
        {"key": "directDoubleCadence", "metricsIndex": 4},
        {"key": "directPower", "metricsIndex": 5},
        {"key": "directElevation", "metricsIndex": 6},
    ]
    metrics = [
        {"metrics": [1790438730000, 0, 2.5, 140, 170, 300, 700]},
        {"metrics": [1790438740000, 500, 3.0, 150, 172, 320, 705]},
        {"metrics": [1790438750000, 1500, 3.5, 160, 174, 340, 712]},
    ]
    activity = SimpleNamespace(metadata_json={
        "garmin_details": {"activityDetailMetrics": metrics, "metricDescriptors": descriptors},
        "garmin_splits": {"splitSummaries": [{
            "splitType": "RWD_RUN", "distance": 1500.0, "duration": 480.0,
            "averageSpeed": 3.1, "averageHR": 150.0, "averagePower": 320.0,
            "maxSpeed": 3.5, "elevationGain": 12.0,
        }]},
    })

    detail = SportAnalysisEngine.activity_detail(activity)

    assert detail["curve"], "la courbe échantillonnée doit être présente"
    assert detail["curve"][0][3] == 140
    assert detail["curve"][0][4] == 170
    assert detail["segments"], "les segments par km doivent être présents"
    segment = detail["segments"][0]
    assert segment[0] == 0
    assert segment[4] == 145
    assert segment[6] == 171
    assert detail["splits"][0]["type"] == "RWD_RUN"
    assert SportAnalysisEngine.activity_detail(SimpleNamespace(metadata_json={})) == {}


def test_summarize_includes_cadence_and_power():
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from app.services.sport_analysis import SportAnalysisEngine

    activity = SimpleNamespace(
        started_at=datetime.now(timezone.utc), sport_type="trail_running",
        distance_m=9000, duration_seconds=3400, elevation_gain_m=250,
        avg_pace_sec_km=377.0, avg_heart_rate=111.0, max_heart_rate=150.0,
        avg_cadence=152.8, avg_power_w=348.0,
    )
    summary = SportAnalysisEngine.summarize([activity])
    assert summary["avg_cadence"] == 152.8
    assert summary["avg_power_w"] == 348.0
