from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.services.sport_analysis import SportAnalysisEngine
from app.services.sport import SportService
from app.schemas.sport import SportDashboardResponse, SportObservationCreate
from app.models.sport import SportActivity, SportActivityAnalysis, SportAthleteObservation, SportCoachConversation, SportCoachMessage


def activity(**values):
    defaults = {
        "started_at": datetime(2026, 9, 20, tzinfo=timezone.utc),
        "sport_type": "running",
        "duration_seconds": 3600,
        "distance_m": 10000,
        "elevation_gain_m": 300,
        "avg_pace_sec_km": 360,
        "avg_heart_rate": 145,
        "max_heart_rate": 170,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def point(index, heart_rate, speed=3.0):
    return SimpleNamespace(
        heart_rate=heart_rate,
        speed_m_s=speed,
        recorded_at=datetime(2026, 9, 20, tzinfo=timezone.utc) + timedelta(seconds=index * 10),
    )


def test_summarize_aggregates_volume_and_sports():
    result = SportAnalysisEngine.summarize([activity(), activity(sport_type="cycling", distance_m=20000)])

    assert result["activity_count"] == 2
    assert result["distance_m"] == 30000
    assert result["elevation_gain_m"] == 600
    assert result["sports"] == {"running": 1, "cycling": 1}


def test_period_comparison_is_previous_equal_length_period():
    current = activity(started_at=datetime(2026, 9, 20, tzinfo=timezone.utc), distance_m=12000)
    previous = activity(started_at=datetime(2026, 9, 13, tzinfo=timezone.utc), distance_m=10000)

    result = SportAnalysisEngine.analyze_period(
        [current, previous], date(2026, 9, 20), date(2026, 9, 20), date(2026, 9, 13)
    )

    assert result["comparison"]["distance_m"] == 20.0
    assert result["comparison_period"] == {"start": date(2026, 9, 13), "end": date(2026, 9, 19)}
    assert result["findings"][0]["evidence"]["current"] == 12000
    assert result["findings"][0]["evidence"]["previous"] == 10000


def test_heart_rate_zones_use_configured_values_and_time():
    item = activity(track_points=[point(0, 120), point(1, 160), point(2, 180)])

    result = SportAnalysisEngine.heart_rate_zones(item, {"max_hr": 200, "rest_hr": 50})

    assert result["time_seconds"]["Z1"] == 10
    assert result["time_seconds"]["Z3"] == 10
    assert result["time_seconds"]["Z4"] == 0


def test_cardiac_drift_requires_recorded_points():
    item = activity(track_points=[SimpleNamespace(heart_rate=140, speed_m_s=3.0)] * 12)

    assert SportAnalysisEngine.cardiac_drift(item) is None


def test_cardiac_drift_is_available_with_enough_samples():
    points = [point(index, 140 if index < 6 else 150) for index in range(12)]

    result = SportAnalysisEngine.cardiac_drift(activity(track_points=points))

    assert result is not None
    assert result["percent"] > 0


def test_training_load_requires_configured_physiological_values():
    item = activity(avg_heart_rate=150, duration_seconds=3600)

    load = SportAnalysisEngine.training_load(item, {"rest_hr": 50, "max_hr": 200})
    unavailable = SportAnalysisEngine.training_load(item)

    assert load["available"] is True
    assert load["score"] == 4000
    assert load["method"] == "duration_minutes_x_hr_reserve_ratio_x_100"
    assert unavailable["available"] is False


def test_athlete_profile_calculates_habitual_weekly_volume():
    activities = [
        activity(started_at=datetime(2026, 9, 7, tzinfo=timezone.utc), distance_m=10000),
        activity(started_at=datetime(2026, 9, 14, tzinfo=timezone.utc), distance_m=20000),
    ]

    profile = SportAnalysisEngine.athlete_profile(activities, [{"name": "Trail", "unit": "km"}])

    assert profile["volume_habitual"]["distance_m_weekly"] == 15000
    assert profile["frequency"]["active_weeks"] == 2
    assert profile["goals"][0]["name"] == "Trail"


def test_goal_analysis_reports_recent_compatible_volume_without_prediction():
    goals = [{"id": 4, "name": "Trail", "goal_type": "distance", "target_value": 130, "unit": "km",
              "target_date": date(2026, 10, 10), "metadata_json": {"sport_type": "trail"}}]
    activities = [activity(started_at=datetime(2026, 9, 20, tzinfo=timezone.utc), sport_type="trail", distance_m=28000)]

    result = SportAnalysisEngine.analyze_goals(goals, activities, date(2026, 9, 23))

    assert result[0]["target"]["distance_m"] == 130000
    assert result[0]["recent_28_days"]["distance_m"] == 28000
    assert result[0]["days_remaining"] == 17
    assert "aucune prédiction" in result[0]["interpretation"]


def test_activity_analysis_model_has_one_cached_record_per_activity():
    assert SportActivityAnalysis.__table__.c.activity_id.unique is True
    assert SportActivityAnalysis.__table__.c.analysis_json.nullable is False


def test_sport_coach_memory_is_scoped_to_athletes():
    assert SportCoachConversation.__table__.c.athlete_id.nullable is False
    assert SportCoachMessage.__table__.c.conversation_id.nullable is False
    assert SportAthleteObservation.__table__.c.athlete_id.nullable is False
    assert SportAthleteObservation.__table__.c.status.default.arg == "calculated"
    assert "goal_analysis" in SportDashboardResponse.model_fields


async def test_coach_persists_conversation_and_user_observation(db_session, auth_user):
    service = SportService(db_session, auth_user)

    answer = await service.coach("Comment va ma semaine ?")
    conversation = await service.get_coach_conversation(answer["conversation_id"])
    observation = await service.create_observation(SportObservationCreate(content="Je prépare un trail."))

    assert answer["message_id"] is not None
    assert [message["role"] for message in conversation["messages"]] == ["user", "assistant"]
    assert observation.status == "confirmed"


async def test_activity_ai_analysis_is_generated_separately_from_import(db_session, auth_user):
    service = SportService(db_session, auth_user)
    athlete = await service.get_or_create_athlete()
    item = SportActivity(athlete_id=athlete.id, sport_type="running", started_at=datetime(2026, 9, 20, tzinfo=timezone.utc), duration_seconds=3600)
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(item)

    await service.generate_activity_ai_analysis(item.id)
    stored = await db_session.scalar(select(SportActivityAnalysis).where(SportActivityAnalysis.activity_id == item.id))

    assert stored is not None
    assert stored.ai_status in {"available", "unavailable"}
    assert stored.ai_attempts == 1
    assert stored.ai_analysis_json["answer"]
