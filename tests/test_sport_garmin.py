from app.services.sport_normalizer import SportNormalizer


def test_gpx_is_normalized_to_sport_activity():
    content = b"""<gpx xmlns="http://www.topografix.com/GPX/1/1">
      <trk><trkseg>
        <trkpt lat="48.1" lon="2.1"><ele>100</ele><time>2026-01-01T10:00:00Z</time></trkpt>
      </trkseg></trk>
    </gpx>"""

    activity = SportNormalizer.from_file("run.gpx", content)

    assert activity.source_type == "gpx"
    assert activity.sport_type == "running"
    assert len(activity.track_points) == 1
    assert activity.track_points[0]["latitude"] == 48.1


def test_mapping_preserves_unknown_metrics_in_metadata():
    activity = SportNormalizer.from_mapping({
        "started_at": "2026-01-01T10:00:00+00:00",
        "sport_type": "trail_running",
        "metadata": {"garmin_custom_metric": 42},
    })

    assert activity.sport_type == "trail_running"
    assert activity.metadata_json["garmin_custom_metric"] == 42


def test_gpx_calculates_core_metrics_from_track_points():
    content = b'''<gpx xmlns="http://www.topografix.com/GPX/1/0"><trk><trkseg>
      <trkpt lat="48.1000" lon="2.1000"><ele>100</ele><time>2026-01-01T10:00:00Z</time></trkpt>
      <trkpt lat="48.1010" lon="2.1000"><ele>110</ele><time>2026-01-01T10:01:00Z</time></trkpt>
    </trkseg></trk></gpx>'''

    activity = SportNormalizer.from_file("run.gpx", content)

    assert activity.duration_seconds == 60
    assert 100 < activity.distance_m < 120
    assert activity.elevation_gain_m == 10
    assert activity.avg_speed_m_s is not None
