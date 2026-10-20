from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# SITES
# ============================================================

class SiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    sort_order: int = Field(0, ge=0)
    is_active: bool = True
    dashboard_visible: bool = True


class SiteUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    sort_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    dashboard_visible: Optional[bool] = None


class SiteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
    is_active: bool
    dashboard_visible: bool
    created_at: datetime
    updated_at: datetime


class SiteListResponse(BaseModel):
    items: List[SiteResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# CARD ALIASES
# ============================================================

class CardAliasCreate(BaseModel):
    alias: str = Field(..., min_length=1, max_length=255)
    user_name: str = Field(..., min_length=1, max_length=100)
    dashboard_visible: bool = True
    is_active: bool = True


class CardAliasUpdate(BaseModel):
    alias: Optional[str] = Field(None, min_length=1, max_length=255)
    user_name: Optional[str] = Field(None, min_length=1, max_length=100)
    dashboard_visible: Optional[bool] = None
    is_active: Optional[bool] = None


class CardAliasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alias: str
    user_name: str
    dashboard_visible: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CardAliasListResponse(BaseModel):
    items: List[CardAliasResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# ACCOUNT CODES
# ============================================================

class AccountCodeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=700)
    label: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)
    dashboard_visible: bool = True
    is_active: bool = True


class AccountCodeUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=100)
    dashboard_visible: Optional[bool] = None
    is_active: Optional[bool] = None


class AccountCodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    label: Optional[str] = None
    category: Optional[str] = None
    dashboard_visible: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AccountCodeListResponse(BaseModel):
    items: List[AccountCodeResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


# ============================================================
# EXPENSES
# ============================================================

class ExpenseUpdate(BaseModel):
    category: Optional[str] = Field(None, max_length=100)
    user_name: Optional[str] = Field(None, max_length=100)
    site_id: Optional[int] = None


class ExpenseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    req_number: int
    expense_date: date
    bank_card: str
    item_description: str
    quantity: int
    uom: Optional[str] = None
    amount: Decimal
    corporation: Optional[int] = None
    cost_center: Optional[int] = None
    account_code: Optional[str] = Field(None, max_length=700)
    account_label: Optional[str] = None
    prepared_by: Optional[str] = None
    category: Optional[str] = None
    category_is_manual: bool
    user_name: Optional[str] = None
    user_is_manual: bool
    site_id: Optional[int] = None
    site: Optional[SiteResponse] = None
    import_reference: Optional[str] = None
    missing_fields: List[str] = []
    is_complete: bool = False
    created_at: datetime
    updated_at: datetime


class ExpenseListResponse(BaseModel):
    items: List[ExpenseResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class BulkSiteAssign(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=1000)
    site_id: int


class BulkSiteResponse(BaseModel):
    updated: int


# ============================================================
# IMPORT
# ============================================================

class ImportBilan(BaseModel):
    rows_total: int = 0
    rows_new: int = 0
    rows_duplicate_existing: int = 0
    rows_duplicate_in_file: int = 0
    rows_unknown_codes: int = 0
    rows_unknown_users: int = 0
    rows_invalid: int = 0


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    reference: str
    file_name: str
    status: str
    created_at: datetime
    validated_at: Optional[datetime] = None
    uploaded_by: Optional[int] = None
    uploaded_by_name: Optional[str] = None
    created_count: Optional[int] = None
    bilan: ImportBilan = ImportBilan()


class StagedRowResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_number: int
    req_number: Optional[int] = None
    expense_date: Optional[date] = None
    bank_card: str
    item_description: str
    quantity: int
    uom: Optional[str] = None
    amount: Decimal
    corporation: Optional[int] = None
    cost_center: Optional[int] = None
    account_code: Optional[str] = None
    account_label: Optional[str] = None
    prepared_by: Optional[str] = None
    invalid_reason: Optional[str] = None
    is_duplicate_existing: bool
    is_duplicate_in_file: bool


class StagedRowListResponse(BaseModel):
    items: List[StagedRowResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ImportValidateResponse(BaseModel):
    reference: str
    created_count: int
    skipped_duplicates: int


class ReassignResponse(BaseModel):
    categories_updated: int
    users_updated: int


# ============================================================
# MESSAGE
# ============================================================

class MessageResponse(BaseModel):
    message: str
