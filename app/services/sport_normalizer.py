from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from app.schemas.sport import SportNormalizedActivity


class SportNormalizer:
    """Converts source-specific activity data into the normalized Sport shape."""

    @staticmethod
    def from_mapping(data: dict[str, Any], source_type: str = "manual") -> SportNormalizedActivity:
        started_at = data.get("started_at") or data.get("start_time")
        if isinstance(started_at, str):
            started_at = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        if not started_at:
            raise ValueError("La date de début de l'activité est obligatoire")
        return SportNormalizedActivity(
            sport_type=data.get("sport_type") or data.get("activity_type") or "other",
            activity_name=data.get("activity_name") or data.get("name"),
            started_at=started_at,
            duration_seconds=int(data.get("duration_seconds") or data.get("duration") or 0),
            distance_m=data.get("distance_m") or data.get("distance"),
            elevation_gain_m=data.get("elevation_gain_m") or data.get("elevation_gain"),
            elevation_loss_m=data.get("elevation_loss_m") or data.get("elevation_loss"),
            avg_speed_m_s=data.get("avg_speed_m_s") or data.get("average_speed"),
            avg_pace_sec_km=data.get("avg_pace_sec_km") or data.get("average_pace"),
            avg_heart_rate=data.get("avg_heart_rate") or data.get("average_heart_rate"),
            max_heart_rate=data.get("max_heart_rate"),
            avg_cadence=data.get("avg_cadence") or data.get("average_cadence"),
            avg_power_w=data.get("avg_power_w") or data.get("average_power"),
            calories=data.get("calories"),
            temperature_c=data.get("temperature_c") or data.get("temperature"),
            source_type=source_type,
            source_file_name=data.get("source_file_name"),
            source_file_path=data.get("source_file_path"),
            external_id=data.get("external_id"),
            metadata_json=data.get("metadata_json") or data.get("metadata") or {},
            track_points=data.get("track_points") or [],
        )

    @classmethod
    def from_file(cls, filename: str, content: bytes) -> SportNormalizedActivity:
        suffix = Path(filename).suffix.lower()
        if suffix == ".gpx":
            return cls._from_gpx(filename, content)
        if suffix == ".tcx":
            return cls._from_tcx(filename, content)
        if suffix == ".fit":
            raise ValueError("L'import FIT nécessite un importateur FIT dédié non installé")
        raise ValueError("Format supporté attendu : GPX ou TCX")

    @staticmethod
    def _from_gpx(filename: str, content: bytes) -> SportNormalizedActivity:
        root = ElementTree.fromstring(content)
        points = []
        for index, point in enumerate(
            element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "trkpt"
        ):
            children = {element.tag.rsplit("}", 1)[-1]: element.text for element in point}
            timestamp = children.get("time")
            elevation = children.get("ele")
            points.append({
                "sequence": index,
                "recorded_at": timestamp,
                "latitude": float(point.attrib["lat"]),
                "longitude": float(point.attrib["lon"]),
                "elevation_m": float(elevation) if elevation else None,
            })
        metadata = {"import_format": "gpx", "point_count": len(points)}
        start = points[0].get("recorded_at") if points else None
        if not start:
            start = datetime.now(timezone.utc).isoformat()
        metrics = SportNormalizer._metrics_from_points(points)
        return SportNormalizedActivity(
            sport_type="running",
            activity_name=Path(filename).stem,
            started_at=datetime.fromisoformat(start.replace("Z", "+00:00")),
            source_type="gpx",
            source_file_name=filename,
            metadata_json=metadata,
            track_points=points,
            **metrics,
        )

    @staticmethod
    def _from_tcx(filename: str, content: bytes) -> SportNormalizedActivity:
        root = ElementTree.fromstring(content)
        namespaces = {"tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
        activity = root.find(".//tcx:Activity", namespaces)
        if activity is None:
            raise ValueError("Aucune activité TCX trouvée")
        sport_type = (activity.attrib.get("Sport") or "other").lower()
        points = []
        for index, trackpoint in enumerate(activity.findall(".//tcx:Trackpoint", namespaces)):
            timestamp = trackpoint.findtext("tcx:Time", namespaces)
            position = trackpoint.find("tcx:Position", namespaces)
            if position is None:
                continue
            lat = position.findtext("tcx:LatitudeDegrees", namespaces)
            lon = position.findtext("tcx:LongitudeDegrees", namespaces)
            if lat is None or lon is None:
                continue
            elevation = trackpoint.findtext("tcx:AltitudeMeters", namespaces)
            points.append({
                "sequence": index,
                "recorded_at": timestamp,
                "latitude": float(lat),
                "longitude": float(lon),
                "elevation_m": float(elevation) if elevation else None,
            })
        start = activity.findtext("tcx:Id", namespaces)
        started_at = datetime.fromisoformat(start.replace("Z", "+00:00")) if start else datetime.now(timezone.utc)
        lap = activity.find(".//tcx:Lap", namespaces)
        summary = {}
        if lap is not None:
            for field in ("TotalTimeSeconds", "DistanceMeters", "Calories", "AverageHeartRateBpm", "MaximumHeartRateBpm"):
                value = lap.findtext(f"tcx:{field}", namespaces)
                if value is not None:
                    summary[field] = value
        metrics = SportNormalizer._metrics_from_points(points)
        if summary.get("TotalTimeSeconds") and (not points or not metrics.get("duration_seconds")):
            metrics["duration_seconds"] = int(float(summary["TotalTimeSeconds"]))
        if summary.get("DistanceMeters") and (not points or not metrics.get("distance_m")):
            metrics["distance_m"] = float(summary["DistanceMeters"])
        if summary.get("Calories"):
            metrics["calories"] = float(summary["Calories"])
        if summary.get("AverageHeartRateBpm"):
            metrics.setdefault("avg_heart_rate", float(summary["AverageHeartRateBpm"]))
        if summary.get("MaximumHeartRateBpm"):
            metrics.setdefault("max_heart_rate", float(summary["MaximumHeartRateBpm"]))
        return SportNormalizedActivity(
            sport_type=sport_type,
            activity_name=Path(filename).stem,
            started_at=started_at,
            source_type="tcx",
            source_file_name=filename,
            metadata_json={"import_format": "tcx", "point_count": len(points)},
            track_points=points,
            **metrics,
        )

    @staticmethod
    def _metrics_from_points(points: list[dict[str, Any]]) -> dict[str, Any]:
        """Calcule les métriques de base quand le fichier ne les fournit pas."""
        if not points:
            return {}
        distance = 0.0
        gain = 0.0
        loss = 0.0
        first_time = last_time = None
        for previous, current in zip(points, points[1:]):
            distance += SportNormalizer._distance_m(
                previous["latitude"], previous["longitude"], current["latitude"], current["longitude"]
            )
            previous_elevation = previous.get("elevation_m")
            current_elevation = current.get("elevation_m")
            if previous_elevation is not None and current_elevation is not None:
                delta = current_elevation - previous_elevation
                if delta > 0:
                    gain += delta
                else:
                    loss -= delta
        timestamps = [point.get("recorded_at") for point in points if point.get("recorded_at")]
        if timestamps:
            first_time = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            last_time = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
        duration = max(0, int((last_time - first_time).total_seconds())) if first_time and last_time else 0
        metrics: dict[str, Any] = {
            "distance_m": distance,
            "elevation_gain_m": gain,
            "elevation_loss_m": loss,
            "duration_seconds": duration,
        }
        if duration > 0 and distance > 0:
            metrics["avg_speed_m_s"] = distance / duration
            metrics["avg_pace_sec_km"] = duration / (distance / 1000)
        return metrics

    @staticmethod
    def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        radius_m = 6_371_000
        lat1, lat2 = math.radians(lat1), math.radians(lat2)
        delta_lat = lat2 - lat1
        delta_lon = math.radians(lon2 - lon1)
        haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        return 2 * radius_m * math.asin(math.sqrt(haversine))
