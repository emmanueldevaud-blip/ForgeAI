import asyncio
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import date

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.agenda import AgendaPresence
from app.models.buildings import Building, Room, UsageType
from app.models.user import User


def normalize(value):
    plain = unicodedata.normalize("NFKD", value.casefold()).encode("ascii", "ignore").decode()
    return tuple(sorted(re.findall(r"[a-z0-9]+", plain)))


async def main(apply_changes):
    records = json.load(sys.stdin)
    input_count = len(records)
    records = [
        dict(row, site="Riom")
        if row["date"] == "2025-11-25" and row["name"] == "Vo, Marion" and row["site"] == "Cébazat"
        else row
        for row in records
    ]
    unique_rows = list({(row["date"], row["name"], row["site"]): row for row in records}.values())
    start = min(date.fromisoformat(row["date"]) for row in unique_rows)
    end = max(date.fromisoformat(row["date"]) for row in unique_rows)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            active_users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()
            users_by_name = {}
            ambiguous_names = set()
            for user in active_users:
                key = normalize(f"{user.first_name or ''} {user.last_name or ''}")
                if key in users_by_name:
                    ambiguous_names.add(key)
                users_by_name[key] = user.id

            bureau_rows = (await db.execute(
                select(Room.id, Room.name, Building.name, UsageType.code, UsageType.name)
                .join(Building, Building.id == Room.building_id)
                .outerjoin(UsageType, UsageType.id == Room.usage_type_id)
                .where(Room.is_active.is_(True), Building.is_active.is_(True))
            )).all()
            room_map = {}
            for site in {row["site"] for row in unique_rows}:
                site_tokens = set(normalize(site))
                candidates = [
                    row[0] for row in bureau_rows
                    if (row[3] in ("BUREAU", "BUREAUX") or (row[4] and "bureau" in row[4].casefold()))
                    and site_tokens.issubset(set(normalize(f"{row[1]} {row[2]}")))
                ]
                if len(candidates) != 1:
                    raise RuntimeError(f"Local Bureau ambigu ou absent pour {site!r}: {candidates}")
                room_map[site] = candidates[0]

            desired = {}
            name_to_user = {}
            for row in unique_rows:
                name_key = normalize(row["name"])
                user_id = None if name_key in ambiguous_names else users_by_name.get(name_key)
                name_to_user[row["name"]] = user_id
                person_key = ("user", user_id) if user_id is not None else ("external", name_key)
                day_key = (date.fromisoformat(row["date"]), person_key)
                room_id = room_map[row["site"]]
                if day_key in desired and desired[day_key]["room_id"] != room_id:
                    previous = desired[day_key]
                    raise RuntimeError(
                        f"Conflit dans le classeur: {row['date']} {row['name']}: "
                        f"{previous['site']} / {row['site']}"
                    )
                desired[day_key] = {
                    "date": day_key[0], "person_key": person_key, "user_id": user_id,
                    "name": row["name"], "room_id": room_id, "site": row["site"],
                }

            existing = (await db.execute(
                select(AgendaPresence).where(
                    AgendaPresence.presence_date >= start,
                    AgendaPresence.presence_date <= end,
                )
            )).scalars().all()
            existing_by_person_day = {}
            for presence in existing:
                if presence.user_id is not None:
                    person_key = ("user", presence.user_id)
                elif presence.external_name:
                    person_key = ("external", normalize(presence.external_name))
                else:
                    continue
                existing_by_person_day.setdefault((presence.presence_date, person_key), []).append(presence)

            conflict_rows = []
            same_room = {}
            for key, target in desired.items():
                found = existing_by_person_day.get(key, [])
                wrong_room = [row for row in found if row.room_id != target["room_id"]]
                if wrong_room:
                    conflict_rows.append((target["date"].isoformat(), target["name"], target["site"], [p.id for p in wrong_room]))
                matching = [row for row in found if row.room_id == target["room_id"]]
                if len(matching) > 1:
                    raise RuntimeError(f"Plusieurs présences existantes pour {target['date']} / {target['name']} / {target['site']}")
                same_room[key] = matching[0] if matching else None
            if conflict_rows:
                raise RuntimeError(f"Présences VPS existantes sur un autre local: {conflict_rows[:20]}")

            created = updated = unchanged = 0
            for key, target in desired.items():
                presence = same_room[key]
                if presence is None:
                    presence = AgendaPresence(
                        presence_date=target["date"], room_id=target["room_id"],
                        user_id=target["user_id"],
                        external_name=None if target["user_id"] is not None else target["name"],
                        source="manual", source_ref="Classeur1.xlsx", is_present=True,
                        needs_workstation=True, needs_meal=True, is_remote=False,
                        period="full", created_by=None,
                    )
                    db.add(presence)
                    created += 1
                elif (presence.is_present, presence.needs_workstation, presence.needs_meal,
                      presence.is_remote, presence.period) != (True, True, True, False, "full"):
                    presence.is_present = True
                    presence.needs_workstation = True
                    presence.needs_meal = True
                    presence.is_remote = False
                    presence.period = "full"
                    updated += 1
                else:
                    unchanged += 1

            if not apply_changes:
                await db.rollback()
            result = {
                "mode": "apply" if apply_changes else "dry_run",
                "input_rows": input_count,
                "deduplicated_rows": len(unique_rows),
                "duplicates_removed_or_site_conflict_resolved": input_count - len(unique_rows),
                "distinct_active_users_matched": len({value for value in name_to_user.values() if value is not None}),
                "user_presences": sum(row["user_id"] is not None for row in desired.values()),
                "free_presences": sum(row["user_id"] is None for row in desired.values()),
                "room_ids": room_map,
                "date_range": [start.isoformat(), end.isoformat()],
                "created": created,
                "updated": updated,
                "already_correct": unchanged,
            }
            print(json.dumps(result, ensure_ascii=False))


asyncio.run(main("--apply" in sys.argv))
