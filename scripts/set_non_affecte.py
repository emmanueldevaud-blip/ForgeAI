from app.db.session import AsyncSessionLocal
from app.models.intendance_expense import IntendanceExpense, IntendanceCategory
from sqlalchemy import select, func, or_
import asyncio

async def fix():
    async with AsyncSessionLocal() as db:
        # Check if "Non affecté" category exists
        result = await db.execute(
            select(IntendanceCategory).where(IntendanceCategory.name == "Non affecté")
        )
        cat = result.scalar_one_or_none()
        
        if not cat:
            cat = IntendanceCategory(name="Non affecté", excluded_from_dashboard=False, is_active=True)
            db.add(cat)
            await db.flush()
            print(f"Created category 'Non affecté' ID={cat.id}")
        else:
            print(f"Category 'Non affecté' exists ID={cat.id}")
        
        # Find expenses with no category
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
        
        print(f"Updating {len(expenses)} expenses to 'Non affecté'...")
        
        for e in expenses:
            e.category = "Non affecté"
            e.category_is_manual = True
        
        await db.commit()
        print("Done!")

asyncio.run(fix())