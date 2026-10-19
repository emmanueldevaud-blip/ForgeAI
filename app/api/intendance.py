"""API du suivi des dépenses de l'Intendance."""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    IntendanceAccountCode, IntendanceCardAlias, IntendanceExpense,
    IntendanceImportBatch, IntendanceImportStagedRow, IntendanceSite, User,
)
from app.schemas.intendance_expense import (
    AccountCodeCreate, AccountCodeListResponse, AccountCodeResponse, AccountCodeUpdate,
    BulkSiteAssign, BulkSiteResponse, ExpenseListResponse, ExpenseResponse,
    ExpenseUpdate, ImportBatchResponse, ImportValidateResponse, SiteCreate,
    SiteListResponse, SiteResponse, SiteUpdate, StagedRowListResponse, StagedRowResponse, ImportBilan,
    CardAliasCreate, CardAliasListResponse, CardAliasResponse, CardAliasUpdate,
)
from app.services.intendance_expense import expense_fingerprint, parse_excel_row

router = APIRouter(prefix="/intendance/expenses", tags=["intendance-expenses"])


def _pages(total: int, page_size: int) -> int:
    return math.ceil(total / page_size) if total else 1


def _expense_response(expense: IntendanceExpense) -> ExpenseResponse:
    missing = []
    if not expense.category:
        missing.append("category")
    if not expense.user_name:
        missing.append("user")
    if not expense.site_id:
        missing.append("site")
    return ExpenseResponse.model_validate(expense).model_copy(update={
        "import_reference": expense.import_batch.reference if expense.import_batch else None,
        "missing_fields": missing,
        "is_complete": not missing,
    })


@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    page: int = 1, page_size: int = 50, search: str | None = None,
    missing: str | None = None, site_id: int | None = None,
    current_user: User = Depends(require_permission("intendance.expenses.view")),
    db: AsyncSession = Depends(get_db),
):
    page = max(page, 1); page_size = min(max(page_size, 1), 500)
    query = select(IntendanceExpense).options(selectinload(IntendanceExpense.site), selectinload(IntendanceExpense.import_batch))
    if search:
        term = f"%{search.strip()}%"
        query = query.where((IntendanceExpense.item_description.ilike(term)) | (IntendanceExpense.bank_card.ilike(term)))
    if site_id is not None:
        query = query.where(IntendanceExpense.site_id == site_id)
    if missing == "site": query = query.where(IntendanceExpense.site_id.is_(None))
    if missing == "category": query = query.where(IntendanceExpense.category.is_(None))
    if missing == "user": query = query.where(IntendanceExpense.user_name.is_(None))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(IntendanceExpense.expense_date.desc(), IntendanceExpense.id.desc()).offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return ExpenseListResponse(items=[_expense_response(row) for row in rows], total=total, page=page, page_size=page_size, total_pages=_pages(total, page_size))


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(expense_id: int, data: ExpenseUpdate, current_user: User = Depends(require_permission("intendance.expenses.edit")), db: AsyncSession = Depends(get_db)):
    expense = (await db.execute(select(IntendanceExpense).options(selectinload(IntendanceExpense.site), selectinload(IntendanceExpense.import_batch)).where(IntendanceExpense.id == expense_id))).scalar_one_or_none()
    if not expense: raise HTTPException(404, "Dépense introuvable")
    changes = data.model_dump(exclude_unset=True)
    if "category" in changes: expense.category_is_manual = True
    if "user_name" in changes: expense.user_is_manual = True
    if "site_id" in changes and changes["site_id"] is not None and not await db.get(IntendanceSite, changes["site_id"]): raise HTTPException(404, "Site introuvable")
    for key, value in changes.items(): setattr(expense, key, value)
    expense.updated_by = current_user.id
    await db.commit(); await db.refresh(expense)
    return _expense_response(expense)


@router.delete("/{expense_id}", status_code=204)
async def delete_expense(expense_id: int, current_user: User = Depends(require_permission("intendance.expenses.edit")), db: AsyncSession = Depends(get_db)):
    expense = await db.get(IntendanceExpense, expense_id)
    if not expense: raise HTTPException(404, "Dépense introuvable")
    await db.delete(expense)
    await db.commit()


@router.post("/sites/bulk", response_model=BulkSiteResponse)
async def bulk_site(data: BulkSiteAssign, current_user: User = Depends(require_permission("intendance.expenses.edit")), db: AsyncSession = Depends(get_db)):
    if not await db.get(IntendanceSite, data.site_id): raise HTTPException(404, "Site introuvable")
    result = await db.execute(select(IntendanceExpense).where(IntendanceExpense.id.in_(data.ids)))
    rows = result.scalars().all()
    for row in rows: row.site_id = data.site_id; row.updated_by = current_user.id
    await db.commit()
    return BulkSiteResponse(updated=len(rows))


@router.get("/sites", response_model=SiteListResponse)
async def list_sites(current_user: User = Depends(require_permission("intendance.expenses.view")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(IntendanceSite).order_by(IntendanceSite.sort_order, IntendanceSite.name))).scalars().all()
    return SiteListResponse(items=[SiteResponse.model_validate(x) for x in rows], total=len(rows), page=1, page_size=len(rows) or 1, total_pages=1)


@router.post("/sites", response_model=SiteResponse, status_code=201)
async def create_site(data: SiteCreate, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    site = IntendanceSite(**data.model_dump()); db.add(site)
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "Ce site existe déjà")
    await db.refresh(site); return SiteResponse.model_validate(site)


@router.patch("/sites/{site_id}", response_model=SiteResponse)
async def update_site(site_id: int, data: SiteUpdate, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    site = await db.get(IntendanceSite, site_id)
    if not site: raise HTTPException(404, "Site introuvable")
    for key, value in data.model_dump(exclude_unset=True).items(): setattr(site, key, value)
    await db.commit(); await db.refresh(site); return SiteResponse.model_validate(site)


@router.delete("/sites/{site_id}", status_code=204)
async def delete_site(site_id: int, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    site = await db.get(IntendanceSite, site_id)
    if not site: raise HTTPException(404, "Site introuvable")
    site.is_active = False
    await db.commit()


@router.get("/account-codes", response_model=AccountCodeListResponse)
async def list_account_codes(current_user: User = Depends(require_permission("intendance.expenses.view")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(IntendanceAccountCode).order_by(IntendanceAccountCode.code))).scalars().all()
    return AccountCodeListResponse(items=[AccountCodeResponse.model_validate(x) for x in rows], total=len(rows), page=1, page_size=len(rows) or 1, total_pages=1)


@router.get("/aliases", response_model=CardAliasListResponse)
async def list_aliases(current_user: User = Depends(require_permission("intendance.expenses.view")), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(IntendanceCardAlias).order_by(IntendanceCardAlias.alias))).scalars().all()
    return CardAliasListResponse(items=[CardAliasResponse.model_validate(x) for x in rows], total=len(rows), page=1, page_size=len(rows) or 1, total_pages=1)


@router.post("/aliases", response_model=CardAliasResponse, status_code=201)
async def create_alias(data: CardAliasCreate, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    alias = IntendanceCardAlias(**data.model_dump()); db.add(alias)
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "Cet alias existe déjà")
    await db.refresh(alias); return CardAliasResponse.model_validate(alias)


@router.patch("/aliases/{alias_id}", response_model=CardAliasResponse)
async def update_alias(alias_id: int, data: CardAliasUpdate, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    alias = await db.get(IntendanceCardAlias, alias_id)
    if not alias: raise HTTPException(404, "Alias introuvable")
    for key, value in data.model_dump(exclude_unset=True).items(): setattr(alias, key, value)
    await db.commit(); await db.refresh(alias); return CardAliasResponse.model_validate(alias)


@router.delete("/aliases/{alias_id}", status_code=204)
async def delete_alias(alias_id: int, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    alias = await db.get(IntendanceCardAlias, alias_id)
    if not alias: raise HTTPException(404, "Alias introuvable")
    await db.delete(alias); await db.commit()


@router.post("/account-codes", response_model=AccountCodeResponse, status_code=201)
async def create_account_code(data: AccountCodeCreate, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    code = IntendanceAccountCode(**data.model_dump()); db.add(code)
    try: await db.commit()
    except IntegrityError: await db.rollback(); raise HTTPException(409, "Ce code existe déjà")
    await db.refresh(code); return AccountCodeResponse.model_validate(code)


@router.patch("/account-codes/{code_id}", response_model=AccountCodeResponse)
async def update_account_code(code_id: int, data: AccountCodeUpdate, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    code = await db.get(IntendanceAccountCode, code_id)
    if not code: raise HTTPException(404, "Code comptable introuvable")
    for key, value in data.model_dump(exclude_unset=True).items(): setattr(code, key, value)
    await db.commit(); await db.refresh(code); return AccountCodeResponse.model_validate(code)


@router.delete("/account-codes/{code_id}", status_code=204)
async def delete_account_code(code_id: int, current_user: User = Depends(require_permission("intendance.expenses.manage_refs")), db: AsyncSession = Depends(get_db)):
    code = await db.get(IntendanceAccountCode, code_id)
    if not code: raise HTTPException(404, "Code comptable introuvable")
    await db.delete(code); await db.commit()


@router.post("/imports", response_model=ImportBatchResponse, status_code=201)
async def analyze_import(file: UploadFile = File(...), current_user: User = Depends(require_permission("intendance.expenses.import")), db: AsyncSession = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xlsx"): raise HTTPException(400, "Seuls les fichiers .xlsx sont acceptés")
    try:
        from openpyxl import load_workbook
        workbook = load_workbook(file.file, read_only=True, data_only=True)
    except Exception as exc: raise HTTPException(400, f"Fichier Excel invalide : {exc}")
    sheet = workbook.active
    headers = [cell.value for cell in next(sheet.iter_rows(max_row=1))]
    expected = ["Req Number", "Detail Required Date", "Bank Card Description", "Item Description", "Quantity", "UOM Code", "DetailExpectedPrice", "Corporation", "Cost Center Code", "Detail Account Description", "Prepared By Name"]
    if headers != expected: raise HTTPException(400, "En-têtes Excel inattendus")
    batch = IntendanceImportBatch(reference=uuid.uuid4().hex, file_name=file.filename, uploaded_by=current_user.id)
    db.add(batch); await db.flush()
    seen = set(); rows = list(sheet.iter_rows(min_row=2, values_only=True)); fingerprints = []
    for number, values in enumerate(rows, 2):
        parsed = parse_excel_row(dict(zip("ABCDEFGHIJK", values)), number); fp = expense_fingerprint(parsed); parsed["fingerprint"] = fp
        parsed["is_duplicate_in_file"] = fp in seen; seen.add(fp); fingerprints.append(fp)
        db.add(IntendanceImportStagedRow(batch_id=batch.id, **{k: v for k, v in parsed.items() if k in {"line_number","fingerprint","req_number","expense_date","bank_card","item_description","quantity","uom","amount","corporation","cost_center","account_code","account_label","prepared_by","invalid_reason","is_duplicate_in_file"}}))
    existing = set((await db.execute(select(IntendanceExpense.fingerprint).where(IntendanceExpense.fingerprint.in_(fingerprints)))).scalars())
    staged = (await db.execute(select(IntendanceImportStagedRow).where(IntendanceImportStagedRow.batch_id == batch.id))).scalars().all()
    for row in staged: row.is_duplicate_existing = row.fingerprint in existing
    batch.rows_total = len(staged); batch.rows_new = sum(not r.invalid_reason and not r.is_duplicate_existing and not r.is_duplicate_in_file for r in staged); batch.rows_duplicate_existing = sum(r.is_duplicate_existing for r in staged); batch.rows_duplicate_in_file = sum(r.is_duplicate_in_file for r in staged); batch.rows_invalid = sum(bool(r.invalid_reason) for r in staged)
    await db.commit(); await db.refresh(batch)
    return ImportBatchResponse(
        id=batch.id, reference=batch.reference, file_name=batch.file_name, status=batch.status,
        created_at=batch.created_at, uploaded_by=batch.uploaded_by,
        bilan=ImportBilan(
            rows_total=batch.rows_total, rows_new=batch.rows_new,
            rows_duplicate_existing=batch.rows_duplicate_existing,
            rows_duplicate_in_file=batch.rows_duplicate_in_file,
            rows_unknown_codes=batch.rows_unknown_codes,
            rows_unknown_users=batch.rows_unknown_users,
            rows_invalid=batch.rows_invalid,
        ),
    )


@router.post("/imports/{batch_id}/validate", response_model=ImportValidateResponse)
async def validate_import(batch_id: int, current_user: User = Depends(require_permission("intendance.expenses.import")), db: AsyncSession = Depends(get_db)):
    batch = (await db.execute(select(IntendanceImportBatch).where(IntendanceImportBatch.id == batch_id).with_for_update())).scalar_one_or_none()
    if not batch: raise HTTPException(404, "Import introuvable")
    if batch.status == "validated": return ImportValidateResponse(reference=batch.reference, created_count=batch.created_count or 0, skipped_duplicates=batch.rows_total - (batch.created_count or 0))
    rows = (await db.execute(select(IntendanceImportStagedRow).where(IntendanceImportStagedRow.batch_id == batch.id))).scalars().all(); created = 0
    aliases = {x.alias: x.user_name for x in (await db.execute(select(IntendanceCardAlias))).scalars().all()}; codes = {x.code: x for x in (await db.execute(select(IntendanceAccountCode))).scalars().all()}
    for row in rows:
        if row.invalid_reason or row.is_duplicate_existing or row.is_duplicate_in_file: continue
        code = codes.get(row.account_code or "")
        db.add(IntendanceExpense(fingerprint=row.fingerprint, req_number=row.req_number, expense_date=row.expense_date, bank_card=row.bank_card, item_description=row.item_description, quantity=row.quantity, uom=row.uom, amount=row.amount, corporation=row.corporation, cost_center=row.cost_center, account_code=row.account_code, account_label=row.account_label, prepared_by=row.prepared_by, category=code.category if code else None, user_name=aliases.get(row.bank_card), import_batch_id=batch.id, created_by=current_user.id)); created += 1
    batch.status = "validated"; batch.validated_at = datetime.now(timezone.utc); batch.created_count = created; await db.commit()
    return ImportValidateResponse(reference=batch.reference, created_count=created, skipped_duplicates=len(rows) - created)


@router.post("/reassign", response_model=dict)
async def reassign_references(current_user: User = Depends(require_permission("intendance.expenses.import")), db: AsyncSession = Depends(get_db)):
    """Réapplique les référentiels configurés sans écraser les corrections manuelles."""
    expenses = (await db.execute(select(IntendanceExpense).with_for_update())).scalars().all()
    aliases = {x.alias: x.user_name for x in (await db.execute(select(IntendanceCardAlias))).scalars().all()}
    codes = {x.code: x.category for x in (await db.execute(select(IntendanceAccountCode))).scalars().all()}
    categories = users = 0
    for expense in expenses:
        if not expense.category_is_manual:
            category = codes.get(expense.account_code or "")
            if expense.category != category:
                expense.category = category
                categories += 1
        if not expense.user_is_manual:
            user_name = aliases.get(expense.bank_card)
            if expense.user_name != user_name:
                expense.user_name = user_name
                users += 1
    await db.commit()
    return {"categories_updated": categories, "users_updated": users}

