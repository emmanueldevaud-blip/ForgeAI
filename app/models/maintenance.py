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
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ============================================================
# PROVIDERS (Prestataires / Fournisseurs)
# ============================================================

class MaintenanceProvider(Base):
    __tablename__ = "maintenance_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    contracts: Mapped[list["MaintenanceContract"]] = relationship(
        "MaintenanceContract", back_populates="provider", cascade="all, delete-orphan"
    )
    work_orders: Mapped[list["MaintenanceWorkOrder"]] = relationship(
        "MaintenanceWorkOrder", back_populates="provider"
    )

    __table_args__ = (
        Index("ix_maintenance_providers_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceProvider(name={self.name})>"


# ============================================================
# CONTRACTS (Contrats de maintenance)
# ============================================================

class MaintenanceContract(Base):
    __tablename__ = "maintenance_contracts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_providers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    renewal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    periodicity: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    provider: Mapped["MaintenanceProvider"] = relationship(
        "MaintenanceProvider", back_populates="contracts"
    )
    equipment_links: Mapped[list["ContractEquipment"]] = relationship(
        "ContractEquipment", back_populates="contract", cascade="all, delete-orphan"
    )
    work_orders: Mapped[list["MaintenanceWorkOrder"]] = relationship(
        "MaintenanceWorkOrder", back_populates="contract"
    )

    __table_args__ = (
        Index("ix_maintenance_contracts_dates", "start_date", "end_date"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceContract(reference={self.reference})>"


class ContractEquipment(Base):
    __tablename__ = "maintenance_contract_equipment"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_contracts.id", ondelete="CASCADE"), nullable=False
    )
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="CASCADE"), nullable=False
    )

    contract: Mapped["MaintenanceContract"] = relationship(
        "MaintenanceContract", back_populates="equipment_links"
    )
    equipment: Mapped["Equipment"] = relationship("Equipment")

    __table_args__ = (
        UniqueConstraint("contract_id", "equipment_id", name="uq_contract_equipment"),
    )


# ============================================================
# PARTS (Pièces et consommables)
# ============================================================

class MaintenancePart(Base):
    __tablename__ = "maintenance_parts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    work_order_links: Mapped[list["WorkOrderPart"]] = relationship(
        "WorkOrderPart", back_populates="part"
    )

    def __repr__(self) -> str:
        return f"<MaintenancePart(reference={self.reference})>"


# ============================================================
# MAINTENANCE REQUESTS (Demandes de maintenance)
# ============================================================

class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    requested_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default="normale", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), default="nouvelle", nullable=False, index=True
    )
    desired_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    equipment: Mapped[Optional["Equipment"]] = relationship("Equipment")
    requested_by_user: Mapped[Optional["User"]] = relationship("User")
    work_orders: Mapped[list["MaintenanceWorkOrder"]] = relationship(
        "MaintenanceWorkOrder", back_populates="request"
    )
    status_history: Mapped[list["MaintenanceStatusHistory"]] = relationship(
        "MaintenanceStatusHistory",
        primaryjoin="and_(MaintenanceStatusHistory.entity_type=='request', "
                    "foreign(MaintenanceStatusHistory.entity_id)==MaintenanceRequest.id)",
        viewonly=True,
    )

    __table_args__ = (
        Index("ix_maintenance_requests_status_priority", "status", "priority"),
        Index("ix_maintenance_requests_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceRequest(number={self.number})>"


# ============================================================
# WORK ORDERS (Ordres de travail)
# ============================================================

class MaintenanceWorkOrder(Base):
    __tablename__ = "maintenance_work_orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    equipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    request_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_providers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_id: Mapped[int | None] = mapped_column(
        ForeignKey("maintenance_contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    responsible_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    maintenance_type: Mapped[str] = mapped_column(
        String(30), default="corrective", nullable=False, index=True
    )
    priority: Mapped[str] = mapped_column(
        String(20), default="normale", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(30), default="nouveau", nullable=False, index=True
    )
    location_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estimated_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    actual_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    diagnosis: Mapped[str | None] = mapped_column(Text, nullable=True)
    cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_performed: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    equipment: Mapped[Optional["Equipment"]] = relationship("Equipment")
    request: Mapped[Optional["MaintenanceRequest"]] = relationship(
        "MaintenanceRequest", back_populates="work_orders"
    )
    provider: Mapped[Optional["MaintenanceProvider"]] = relationship(
        "MaintenanceProvider", back_populates="work_orders"
    )
    contract: Mapped[Optional["MaintenanceContract"]] = relationship(
        "MaintenanceContract", back_populates="work_orders"
    )
    responsible: Mapped[Optional["User"]] = relationship("User")
    intervenants: Mapped[list["MaintenanceIntervenant"]] = relationship(
        "MaintenanceIntervenant", back_populates="work_order", cascade="all, delete-orphan"
    )
    interventions: Mapped[list["MaintenanceIntervention"]] = relationship(
        "MaintenanceIntervention", back_populates="work_order", cascade="all, delete-orphan"
    )
    parts_used: Mapped[list["WorkOrderPart"]] = relationship(
        "WorkOrderPart", back_populates="work_order", cascade="all, delete-orphan"
    )
    costs: Mapped[list["MaintenanceCost"]] = relationship(
        "MaintenanceCost", back_populates="work_order", cascade="all, delete-orphan"
    )
    status_history: Mapped[list["MaintenanceStatusHistory"]] = relationship(
        "MaintenanceStatusHistory",
        primaryjoin="and_(MaintenanceStatusHistory.entity_type=='work_order', "
                    "foreign(MaintenanceStatusHistory.entity_id)==MaintenanceWorkOrder.id)",
        viewonly=True,
    )

    __table_args__ = (
        Index("ix_maintenance_wo_status_priority", "status", "priority"),
        Index("ix_maintenance_wo_planned", "planned_date"),
        Index("ix_maintenance_wo_type_status", "maintenance_type", "status"),
    )

    def __repr__(self) -> str:
        return f"<MaintenanceWorkOrder(number={self.number})>"


# ============================================================
# INTERVENANTS (Sur ordres de travail)
# ============================================================

class MaintenanceIntervenant(Base):
    __tablename__ = "maintenance_intervenants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    role_in_intervention: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hours_spent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="intervenants"
    )
    user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_maintenance_intervenants_wo_user", "work_order_id", "user_id"),
    )


# ============================================================
# INTERVENTIONS (Détails interventions)
# ============================================================

class MaintenanceIntervention(Base):
    __tablename__ = "maintenance_interventions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    intervention_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_performed: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="interventions"
    )


# ============================================================
# MAINTENANCE PLANS (Plans préventifs)
# ============================================================

class MaintenancePlan(Base):
    __tablename__ = "maintenance_plans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    intervention_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    frequency: Mapped[str] = mapped_column(String(30), nullable=False)
    frequency_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    next_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    estimated_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="normale", nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    equipment: Mapped["Equipment"] = relationship("Equipment")
    checklist_items: Mapped[list["MaintenancePlanChecklist"]] = relationship(
        "MaintenancePlanChecklist", back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_maintenance_plans_equipment_active", "equipment_id", "is_active"),
        Index("ix_maintenance_plans_next_due", "next_due_date"),
    )

    def __repr__(self) -> str:
        return f"<MaintenancePlan(title={self.title})>"


class MaintenancePlanChecklist(Base):
    __tablename__ = "maintenance_plan_checklist"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    plan: Mapped["MaintenancePlan"] = relationship(
        "MaintenancePlan", back_populates="checklist_items"
    )


# ============================================================
# WORK ORDER PARTS (Pièces utilisées sur OT)
# ============================================================

class WorkOrderPart(Base):
    __tablename__ = "maintenance_work_order_parts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    part_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_parts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="parts_used"
    )
    part: Mapped["MaintenancePart"] = relationship(
        "MaintenancePart", back_populates="work_order_links"
    )

    __table_args__ = (
        Index("ix_maintenance_wo_parts_wo", "work_order_id"),
    )


# ============================================================
# COSTS (Coûts de maintenance)
# ============================================================

class MaintenanceCost(Base):
    __tablename__ = "maintenance_costs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cost_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    work_order: Mapped["MaintenanceWorkOrder"] = relationship(
        "MaintenanceWorkOrder", back_populates="costs"
    )

    __table_args__ = (
        Index("ix_maintenance_costs_wo_type", "work_order_id", "cost_type"),
    )


# ============================================================
# STATUS HISTORY (Historique des statuts)
# ============================================================

class MaintenanceStatusHistory(Base):
    __tablename__ = "maintenance_status_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    changed_by_user: Mapped[Optional["User"]] = relationship("User")

    __table_args__ = (
        Index("ix_maintenance_status_history_entity", "entity_type", "entity_id"),
    )


# ============================================================
# AI CONVERSATIONS (Assistant IA transverse)
# ============================================================

class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User")
    messages: Mapped[list["AIMessage"]] = relationship(
        "AIMessage", back_populates="conversation", cascade="all, delete-orphan",
        order_by="AIMessage.created_at"
    )

    __table_args__ = (
        Index("ix_ai_conversations_user_module", "user_id", "module"),
    )


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["AIConversation"] = relationship(
        "AIConversation", back_populates="messages"
    )
