from types import SimpleNamespace

import pytest

from app.services.sport_editorial_engine import (
    analyze_activity,
    build_editorial_brief,
    build_hashtags,
    choose_direction,
)


def activity(**overrides):
    values = {
        "sport_type": "trail_running",
        "distance_m": 32000,
        "duration_seconds": 10800,
        "elevation_gain_m": 1450,
        "avg_pace_sec_km": 405,
        "metadata_json": {"location": "Beaujolais"},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_analyse_long_mountain_activity_without_invention():
    result = analyze_activity(activity())
    assert result.distance_km == 32.0
    assert "sortie_longue" in result.characteristics
    assert "fort_denivele" in result.characteristics
    assert result.location == "Beaujolais"


def test_small_activity_gets_a_different_direction():
    result = analyze_activity(activity(distance_m=5000, duration_seconds=1500, elevation_gain_m=40))
    direction = choose_direction(result, photo_count=1)
    assert direction.primary == "humour"


def test_hashtags_are_limited_and_keep_brand_signature():
    tags = build_hashtags(analyze_activity(activity()))
    assert tags[-1].lower() == "#jepepagtrail"
    assert len(tags) <= 3


def test_brief_contains_memory_and_photo_count():
    brief = build_editorial_brief(activity(), photo_count=3)
    assert brief["photo_count"] == 3
    assert brief["direction"]["template"] == "mountain-card"
    assert brief["memory"] == {"titles": [], "captions": [], "styles": []}


def test_sparse_activity_does_not_invent_location_or_characteristic():
    result = analyze_activity(activity(
        sport_type="running",
        distance_m=None,
        duration_seconds=0,
        elevation_gain_m=None,
        avg_pace_sec_km=None,
        metadata_json={},
    ))
    assert result.location is None
    assert result.characteristics == ("sortie_reguliere",)
    assert result.confidence == "low"


def test_memory_keeps_recent_titles_and_styles():
    previous = [
        SimpleNamespace(
            title="Montée au sommet",
            content="Une sortie qui pique.",
            design={"editorial_engine": {"style": "aventure"}},
        )
    ]
    brief = build_editorial_brief(activity(), recent_publications=previous)
    assert brief["memory"]["titles"] == ["Montée au sommet"]
    assert brief["memory"]["styles"] == ["aventure"]


@pytest.mark.parametrize(
    ("distance", "elevation", "expected"),
    [
        (5000, 40, "humour"),
        (12000, 250, "souvenir"),
        (32000, 1450, "aventure"),
        (28000, 400, "performance"),
    ],
)
def test_direction_matrix(distance, elevation, expected):
    # Durée neutre : la matrice vérifie ici distance/dénivelé, pas l'endurance.
    result = analyze_activity(activity(
        distance_m=distance,
        duration_seconds=3600,
        elevation_gain_m=elevation,
    ))
    assert choose_direction(result, photo_count=1).primary == expected
