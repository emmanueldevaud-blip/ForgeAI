"""Service d'import occupation logements depuis Excel."""
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.housing import Housing, Occupancy, Occupant
from app.models.buildings import Room, Building


MONTHS = {
    "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "aout": 8, "août": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12,
}


def norm(value: Any) -> str:
    if value is None:
        return ""
    value = str(value)
    value = "".join(c for c in value if c.isalnum() or c.isspace())
    value = re.sub(r"\s+", " ", value.lower())
    return value.strip()


def parse_occupant_name(label: str) -> tuple[str, str]:
    """Parse 'Prénom NOM' or 'NOM Prénom' or 'Prénom1 et Prénom2 NOM'."""
    label = " ".join(str(label).split())
    if not label:
        return "", ""
    
    # "Préparation chambre" -> ignore
    if label.lower() in ("preparation chambre", "preparation", "ménage", "menage"):
        return "", ""
    
    # "Prénom1 et Prénom2 NOM" -> couple
    if " et " in label.lower():
        parts = label.split(" et ")
        if len(parts) == 2:
            p1, p2 = parts[0].strip(), parts[1].strip()
            # Assume both share last name
            return p2, p1  # last, first (combined)
    
    parts = label.split(" ")
    if len(parts) >= 2:
        # Try to detect "NOM Prénom" vs "Prénom NOM"
        # If first part is all caps or first letter caps + rest lower -> likely NOM
        first = parts[0]
        if first.isupper() or (first[0].isupper() and first[1:].islower()):
            # Likely "NOM Prénom..."
            return first, " ".join(parts[1:])
        else:
            # Likely "Prénom NOM..."
            return parts[-1], " ".join(parts[:-1])
    return label, ""


async def find_or_create_occupant(db: AsyncSession, raw_label: str) -> list[Occupant]:
    """Find existing occupants or create new ones from label."""
    last, first = parse_occupant_name(raw_label)
    if not last and not first:
        return []
    
    nlast, nfirst = norm(last), norm(first)
    
    # Search existing
    stmt = select(Occupant).where(Occupant.is_active.is_(True))
    occupants = (await db.execute(stmt)).scalars().all()
    
    candidates = []
    for o in occupants:
        o_last, o_first = norm(o.last_name or ""), norm(o.first_name or "")
        if o_last == nlast and o_first == nfirst:
            candidates.append(o)
        elif o_last == nfirst and o_first == nlast:
            candidates.append(o)
    
    if len(candidates) == 1:
        return candidates
    elif len(candidates) > 1:
        return candidates  # ambiguous
    
    # Not found -> create new
    new_occ = Occupant(
        last_name=last,
        first_name=first,
        is_active=True,
    )
    db.add(new_occ)
    await db.flush()
    return [new_occ]


def parse_room_label(label: str) -> tuple[str, int] | None:
    """Map Excel column label to (housing_name, room_index)."""
    label = norm(label)
    
    mapping = {
        "les sentiers chambre 1": ("Les Sentiers", 0),
        "les sentiers chambre 2": ("Les Sentiers", 1),
        "le puy de dome": ("Le Puy de Dôme", 0),
        "les sources chambre 1": ("Les Sources", 0),
        "les sources chambre 2": ("Les Sources", 1),
        "le pariou chambre 2": ("Le Pariou", 1),
        "le pariou chambre 1": ("Le Pariou", 0),
        "le sancy chambre 1": ("Le Sancy", 0),
    }
    return mapping.get(label)


async def get_housing_by_name(db: AsyncSession, name: str) -> Housing | None:
    stmt = select(Housing).join(Room, Room.id == Housing.room_id).join(Building, Building.id == Room.building_id).where(
        Housing.is_active.is_(True),
        Room.is_active.is_(True),
        Building.is_active.is_(True),
    )
    housings = (await db.execute(stmt)).scalars().all()
    for h in housings:
        r = await db.get(Room, h.room_id)
        b = await db.get(Building, r.building_id) if r else None
        if b and norm(b.name) == norm(name):
            return h
    return None


async def get_or_create_housing(db: AsyncSession, name: str, nb_rooms: int = 1, room_names: list[str] = None) -> Housing:
    """Get existing housing or create it with room."""
    existing = await get_housing_by_name(db, name)
    if existing:
        return existing
    
    # Need to create room first
    room = Room(
        name=name,
        building_id=1,  # default building, adjust if needed
        is_active=True,
    )
    db.add(room)
    await db.flush()
    
    housing = Housing(
        room_id=room.id,
        housing_type="standard",
        nb_rooms=nb_rooms,
        room_names=room_names or [f"Chambre {i+1}" for i in range(nb_rooms)],
        is_active=True,
    )
    db.add(housing)
    await db.flush()
    return housing


async def analyze_import(
    db: AsyncSession,
    file_content: bytes,
    filename: str,
    uploaded_by: int,
) -> dict:
    """Parse Excel, detect stays, return analysis without writing to DB yet."""
    workbook = openpyxl.load_workbook(BytesIO(file_content), data_only=True)
    ws = workbook["Occupation_2026"]
    
    # Parse header row
    header = list(ws.iter_rows(min_row=1, max_row=1, values_only=True))[0]
    date_col = header[0]
    room_cols = [(i, h) for i, h in enumerate(header) if i > 0 and h]
    
    # Build room mapping
    room_mapping = {}
    for idx, label in room_cols:
        parsed = parse_room_label(label)
        if parsed:
            housing_name, room_index = parsed
            room_mapping[idx] = (housing_name, room_index, label)
    
    if not room_mapping:
        raise ValueError("Aucune colonne chambre reconnue")
    
    # Parse all rows, group consecutive nights by (occupant, housing, room_index)
    raw_rows = list(ws.iter_rows(min_row=2, values_only=True))
    
    # For each room column, track consecutive stays
    stays: dict[tuple, list[dict]] = defaultdict(list)
    
    for row in raw_rows:
        occupancy_date = row[0]
        if isinstance(occupancy_date, datetime):
            stay_date = occupancy_date.date()
        elif isinstance(occupancy_date, date):
            stay_date = occupancy_date
        else:
            continue
        
        for idx, (housing_name, room_index, orig_label) in room_mapping.items():
            occupant_label = row[idx] if idx < len(row) else None
            if not occupant_label or not str(occupant_label).strip():
                continue
            
            occupants = await find_or_create_occupant(db, str(occupant_label).strip())
            if not occupants:
                continue
            
            # Use first occupant as primary
            primary_occ = occupants[0]
            housing = await get_or_create_housing(db, housing_name)
            
            key = (primary_occ.id, housing.id, room_index)
            stays[key].append({
                "date": stay_date,
                "occupants": occupants,
                "occupant_label": str(occupant_label).strip(),
            })
    
    # Group consecutive nights into stays
    grouped_stays = []
    for key, nights in stays.items():
        nights_sorted = sorted(nights, key=lambda x: x["date"])
        current_start = nights_sorted[0]["date"]
        current_end = nights_sorted[0]["date"]
        current_occupants = nights_sorted[0]["occupants"]
        
        for night in nights_sorted[1:]:
            if night["date"] == current_end + timedelta(days=1) and night["occupants"] == current_occupants:
                current_end = night["date"]
            else:
                # Save previous stay
                grouped_stays.append({
                    "occupant_id": key[0],
                    "occupant_label": current_occupants[0].last_name + " " + current_occupants[0].first_name,
                    "housing_id": key[1],
                    "room_index": key[2],
                    "arrival_date": datetime.combine(current_start, datetime.min.time()),
                    "departure_date": datetime.combine(current_end + timedelta(days=1), datetime.min.time()),
                    "nb_nights": (current_end - current_start).days + 1,
                    "occupants": current_occupants,
                })
                current_start = night["date"]
                current_end = night["date"]
                current_occupants = night["occupants"]
        
        # Last stay
        grouped_stays.append({
            "occupant_id": key[0],
            "occupant_label": current_occupants[0].last_name + " " + current_occupants[0].first_name,
            "housing_id": key[1],
            "room_index": key[2],
            "arrival_date": datetime.combine(current_start, datetime.min.time()),
            "departure_date": datetime.combine(current_end + timedelta(days=1), datetime.min.time()),
            "nb_nights": (current_end - current_start).days + 1,
            "occupants": current_occupants,
        })
    
    # Check duplicates in DB
    from app.models.housing import Occupancy
    stats = {
        "total_stays": len(grouped_stays),
        "ready": 0,
        "duplicate": 0,
        "ambiguous": 0,
    }
    
    for stay in grouped_stays:
        # Check existing occupancy for same housing, room, dates
        existing = await db.execute(
            select(Occupancy.id).where(
                Occupancy.housing_id == stay["housing_id"],
                Occupancy.room_index == stay["room_index"],
                Occupancy.arrival_date == stay["arrival_date"],
                Occupancy.departure_date == stay["departure_date"],
            )
        )
        if existing.scalar_one_or_none():
            stay["status"] = "duplicate"
            stats["duplicate"] += 1
        elif len(stay["occupants"]) > 1:
            stay["status"] = "ambiguous"
            stats["ambiguous"] += 1
        else:
            stay["status"] = "ready"
            stats["ready"] += 1
    
    return {
        "filename": filename,
        "stats": stats,
        "stays": grouped_stays,
        "period_start": min(s["arrival_date"] for s in grouped_stays) if grouped_stays else None,
        "period_end": max(s["departure_date"] for s in grouped_stays) if grouped_stays else None,
    }


async def validate_import(db: AsyncSession, stays: list[dict], uploaded_by: int) -> tuple[int, int]:
    """Create occupancies for ready stays. Returns (created, skipped)."""
    from app.models.housing import Occupancy, Occupant, occupancy_occupants
    
    created = 0
    skipped = 0
    
    for stay in stays:
        if stay.get("status") != "ready":
            continue
        
        # Double-check duplicate
        existing = await db.execute(
            select(Occupancy.id).where(
                Occupancy.housing_id == stay["housing_id"],
                Occupancy.room_index == stay["room_index"],
                Occupancy.arrival_date == stay["arrival_date"],
                Occupancy.departure_date == stay["departure_date"],
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        
        occupancy = Occupancy(
            housing_id=stay["housing_id"],
            room_index=stay["room_index"],
            arrival_date=stay["arrival_date"],
            departure_date=stay["departure_date"],
            status="confirmed",
            nb_persons=len(stay.get("occupants", [])),
            created_by=uploaded_by,
        )
        db.add(occupancy)
        await db.flush()
        
        # Link occupants - fetch from DB by ID
        occupant_ids = [o["id"] if isinstance(o, dict) else o.id for o in stay.get("occupants", [])]
        if occupant_ids:
            result = await db.execute(
                select(Occupant).where(Occupant.id.in_(occupant_ids))
            )
            occupants = result.scalars().all()
            
            for i, occ in enumerate(occupants):
                await db.execute(
                    occupancy_occupants.insert().values(
                        occupancy_id=occupancy.id,
                        occupant_id=occ.id,
                        is_primary=(i == 0),
                    )
                )
        
        created += 1
    
    await db.commit()
    return created, skipped