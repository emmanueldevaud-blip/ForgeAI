from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class IntendanceSite(Base):
    __tablename__ = "intendance_sites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    dashboard_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    expenses: Mapped[list["IntendanceExpense"]] = relationship("IntendanceExpense", back_populates="site")

    def __repr__(self) -> str:
        return f"<IntendanceSite(name={self.name})>"


class IntendanceCardAlias(Base):
    __tablename__ = "intendance_card_aliases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    alias: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    user_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dashboard_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<IntendanceCardAlias(alias={self.alias}, user={self.user_name})>"


class IntendanceAccountCode(Base):
    __tablename__ = "intendance_account_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(700), unique=True, nullable=False, index=True)
    label: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    dashboard_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<IntendanceAccountCode(code={self.code}, category={self.category})>"


class IntendanceCategory(Base):
    __tablename__ = "intendance_categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    excluded_from_dashboard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IntendanceDashboardSetting(Base):
    __tablename__ = "intendance_dashboard_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    exclude_uncategorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class IntendanceImportBatch(Base):
    __tablename__ = "intendance_import_batches"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="analyzed", nullable=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rows_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_duplicate_existing: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_duplicate_in_file: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_unknown_codes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_unknown_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_invalid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    staged_rows: Mapped[list["IntendanceImportStagedRow"]] = relationship(
        "IntendanceImportStagedRow",
        back_populates="batch",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<IntendanceImportBatch(reference={self.reference}, status={self.status})>"


class IntendanceImportStagedRow(Base):
    __tablename__ = "intendance_import_staged_rows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("intendance_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    req_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    bank_card: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    item_description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    corporation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_center: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_code: Mapped[str | None] = mapped_column(String(700), nullable=True)
    account_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    invalid_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_duplicate_existing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_duplicate_in_file: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    batch: Mapped[IntendanceImportBatch] = relationship("IntendanceImportBatch", back_populates="staged_rows")

    def __repr__(self) -> str:
        return f"<IntendanceImportStagedRow(batch={self.batch_id}, line={self.line_number})>"


class IntendanceExpense(Base):
    __tablename__ = "intendance_expenses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    req_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    expense_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    bank_card: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    uom: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    corporation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_center: Mapped[int | None] = mapped_column(Integer, nullable=True)
    account_code: Mapped[str | None] = mapped_column(String(700), nullable=True, index=True)
    account_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    prepared_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    category_is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    user_is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    site_id: Mapped[int | None] = mapped_column(
        ForeignKey("intendance_sites.id", ondelete="SET NULL"), nullable=True, index=True
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("intendance_import_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    site: Mapped[Optional[IntendanceSite]] = relationship("IntendanceSite", back_populates="expenses")
    import_batch: Mapped[Optional[IntendanceImportBatch]] = relationship("IntendanceImportBatch")
    history: Mapped[list["IntendanceExpenseHistory"]] = relationship(
        "IntendanceExpenseHistory", back_populates="expense", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_intendance_expenses_category_manual", "category", "category_is_manual"),
        Index("ix_intendance_expenses_user_manual", "user_name", "user_is_manual"),
    )

    def __repr__(self) -> str:
        return f"<IntendanceExpense(id={self.id}, req_number={self.req_number}, amount={self.amount})>"


class IntendanceExpenseHistory(Base):
    __tablename__ = "intendance_expense_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("intendance_expenses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    expense: Mapped[IntendanceExpense] = relationship("IntendanceExpense", back_populates="history")

    __table_args__ = (
        Index("ix_intendance_expense_history_expense_changed", "expense_id", "changed_at"),
    )

    def __repr__(self) -> str:
        return f"<IntendanceExpenseHistory(expense={self.expense_id}, field={self.field_name})>"
