from app.db.session import AsyncSessionLocal
from app.models.intendance_expense import IntendanceExpense, IntendanceCategory
from sqlalchemy import select, func, or_
import asyncio

async def check():
    async with AsyncSessionLocal() as db:
        # Find expenses with no category or "Non classé"
        result = await db.execute(
            select(IntendanceExpense).where(
                or_(
                    IntendanceExpense.category.is_(None),
                    IntendanceExpense.category == '',
                    IntendanceExpense.category == 'Non classé',
                    IntendanceExpense.category == 'Non affecté'
                )
            )
        )
        expenses = result.scalars().all()
        
        print(f"Expenses with no category or 'Non classé/affecté': {len(expenses)}")
        
        # Also check for no site
        result = await db.execute(
            select(func.count()).select_from(IntendanceExpense).where(IntendanceExpense.site_id.is_(None))
        )
        print(f"Expenses with no site: {result.scalar_one()}")
        
        # Also check for no user
        result = await db.execute(
            select(func.count()).select_from(IntendanceExpense).where(
                or_(IntendanceExpense.user_name.is_(None), IntendanceExpense.user_name == '')
            )
        )
        print(f"Expenses with no user: {result.scalar_one()}")
        
        # Show sample
        for e in expenses[:20]:
            print(f"  ID={e.id}, req={e.req_number}, cat='{e.category}', site={e.site_id}, user='{e.user_name}', desc={e.item_description[:50]}")

asyncio.run(check())