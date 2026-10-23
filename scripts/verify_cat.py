from app.db.session import AsyncSessionLocal
from app.models.intendance_expense import IntendanceExpense
from sqlalchemy import select, func, or_
import asyncio

async def check():
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(func.count()).select_from(IntendanceExpense).where(or_(IntendanceExpense.category.is_(None), IntendanceExpense.category == "")))
        print(f"Still null/empty: {r.scalar_one()}")
        r = await db.execute(select(func.count()).select_from(IntendanceExpense).where(IntendanceExpense.category == "Non affecté"))
        print(f"Non affecté: {r.scalar_one()}")

asyncio.run(check())