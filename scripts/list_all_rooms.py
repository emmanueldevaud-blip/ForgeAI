#!/usr/bin/env python3
from app.db.session import AsyncSessionLocal
from app.models.buildings import Room
from sqlalchemy import select
import asyncio

async def q():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(Room))
        for x in r.scalars().all():
            print(f"{x.id}: '{x.name}' (building_id={x.building_id})")

asyncio.run(q())