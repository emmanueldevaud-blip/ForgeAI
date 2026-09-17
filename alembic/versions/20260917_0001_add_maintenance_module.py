"""add_maintenance_module

Revision ID: 20260917_0001
Revises: 20260916_0002
Create Date: 2026-09-17
"""

from alembic import op
import sqlalchemy as sa

revision = "20260917_0001"
down_revision = "20260916_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # PROVIDERS
    # ============================================================
    op.create_table(
        "maintenance_providers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("contract_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_providers_active", "maintenance_providers", ["is_active"])

    # ============================================================
    # CONTRACTS
    # ============================================================
    op.create_table(
        "maintenance_contracts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("maintenance_providers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("renewal_date", sa.Date(), nullable=True),
        sa.Column("cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("periodicity", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_maintenance_contract_ref"),
    )
    op.create_index("ix_maintenance_contracts_provider", "maintenance_contracts", ["provider_id"])
    op.create_index("ix_maintenance_contracts_dates", "maintenance_contracts", ["start_date", "end_date"])

    # ============================================================
    # CONTRACT EQUIPMENT (M2M)
    # ============================================================
    op.create_table(
        "maintenance_contract_equipment",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("maintenance_contracts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipments.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "equipment_id", name="uq_contract_equipment"),
    )

    # ============================================================
    # PARTS
    # ============================================================
    op.create_table(
        "maintenance_parts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference", name="uq_maintenance_part_ref"),
    )

    # ============================================================
    # MAINTENANCE REQUESTS
    # ============================================================
    op.create_table(
        "maintenance_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normale"),
        sa.Column("status", sa.String(30), nullable=False, server_default="nouvelle"),
        sa.Column("desired_date", sa.Date(), nullable=True),
        sa.Column("location_summary", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="uq_maintenance_request_number"),
    )
    op.create_index("ix_maintenance_requests_equipment", "maintenance_requests", ["equipment_id"])
    op.create_index("ix_maintenance_requests_requested_by", "maintenance_requests", ["requested_by"])
    op.create_index("ix_maintenance_requests_priority", "maintenance_requests", ["priority"])
    op.create_index("ix_maintenance_requests_status", "maintenance_requests", ["status"])
    op.create_index("ix_maintenance_requests_status_priority", "maintenance_requests", ["status", "priority"])
    op.create_index("ix_maintenance_requests_created", "maintenance_requests", ["created_at"])

    # ============================================================
    # WORK ORDERS
    # ============================================================
    op.create_table(
        "maintenance_work_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_id", sa.Integer(), sa.ForeignKey("maintenance_requests.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_id", sa.Integer(), sa.ForeignKey("maintenance_providers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contract_id", sa.Integer(), sa.ForeignKey("maintenance_contracts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("responsible_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("maintenance_type", sa.String(30), nullable=False, server_default="corrective"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normale"),
        sa.Column("status", sa.String(30), nullable=False, server_default="nouveau"),
        sa.Column("location_summary", sa.String(500), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estimated_duration_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("actual_duration_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("diagnosis", sa.Text(), nullable=True),
        sa.Column("cause", sa.Text(), nullable=True),
        sa.Column("work_performed", sa.Text(), nullable=True),
        sa.Column("solution", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="uq_maintenance_wo_number"),
    )
    op.create_index("ix_maintenance_wo_equipment", "maintenance_work_orders", ["equipment_id"])
    op.create_index("ix_maintenance_wo_request", "maintenance_work_orders", ["request_id"])
    op.create_index("ix_maintenance_wo_provider", "maintenance_work_orders", ["provider_id"])
    op.create_index("ix_maintenance_wo_contract", "maintenance_work_orders", ["contract_id"])
    op.create_index("ix_maintenance_wo_responsible", "maintenance_work_orders", ["responsible_id"])
    op.create_index("ix_maintenance_wo_maintenance_type", "maintenance_work_orders", ["maintenance_type"])
    op.create_index("ix_maintenance_wo_priority", "maintenance_work_orders", ["priority"])
    op.create_index("ix_maintenance_wo_status", "maintenance_work_orders", ["status"])
    op.create_index("ix_maintenance_wo_status_priority", "maintenance_work_orders", ["status", "priority"])
    op.create_index("ix_maintenance_wo_planned", "maintenance_work_orders", ["planned_date"])
    op.create_index("ix_maintenance_wo_type_status", "maintenance_work_orders", ["maintenance_type", "status"])
    op.create_index("ix_maintenance_wo_created", "maintenance_work_orders", ["created_at"])

    # ============================================================
    # INTERVENANTS
    # ============================================================
    op.create_table(
        "maintenance_intervenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("role_in_intervention", sa.String(100), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hours_spent", sa.Numeric(6, 2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_intervenants_wo", "maintenance_intervenants", ["work_order_id"])
    op.create_index("ix_maintenance_intervenants_user", "maintenance_intervenants", ["user_id"])
    op.create_index("ix_maintenance_intervenants_wo_user", "maintenance_intervenants", ["work_order_id", "user_id"])

    # ============================================================
    # INTERVENTIONS
    # ============================================================
    op.create_table(
        "maintenance_interventions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("intervention_date", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("work_performed", sa.Text(), nullable=True),
        sa.Column("duration_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_interventions_wo", "maintenance_interventions", ["work_order_id"])

    # ============================================================
    # MAINTENANCE PLANS
    # ============================================================
    op.create_table(
        "maintenance_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("intervention_type", sa.String(100), nullable=True),
        sa.Column("frequency", sa.String(30), nullable=False),
        sa.Column("frequency_value", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("next_due_date", sa.Date(), nullable=True),
        sa.Column("estimated_duration_hours", sa.Numeric(6, 2), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normale"),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_plans_equipment", "maintenance_plans", ["equipment_id"])
    op.create_index("ix_maintenance_plans_equipment_active", "maintenance_plans", ["equipment_id", "is_active"])
    op.create_index("ix_maintenance_plans_next_due", "maintenance_plans", ["next_due_date"])
    op.create_index("ix_maintenance_plans_frequency", "maintenance_plans", ["frequency"])

    # ============================================================
    # PLAN CHECKLIST
    # ============================================================
    op.create_table(
        "maintenance_plan_checklist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("maintenance_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_plan_checklist_plan", "maintenance_plan_checklist", ["plan_id"])

    # ============================================================
    # WORK ORDER PARTS
    # ============================================================
    op.create_table(
        "maintenance_work_order_parts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("maintenance_parts.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("unit_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_wo_parts_wo", "maintenance_work_order_parts", ["work_order_id"])
    op.create_index("ix_maintenance_wo_parts_part", "maintenance_work_order_parts", ["part_id"])

    # ============================================================
    # COSTS
    # ============================================================
    op.create_table(
        "maintenance_costs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("maintenance_work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cost_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_costs_wo", "maintenance_costs", ["work_order_id"])
    op.create_index("ix_maintenance_costs_wo_type", "maintenance_costs", ["work_order_id", "cost_type"])

    # ============================================================
    # STATUS HISTORY
    # ============================================================
    op.create_table(
        "maintenance_status_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(30), nullable=True),
        sa.Column("new_status", sa.String(30), nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_maintenance_sh_entity_type", "maintenance_status_history", ["entity_type"])
    op.create_index("ix_maintenance_sh_entity_id", "maintenance_status_history", ["entity_id"])
    op.create_index("ix_maintenance_sh_entity", "maintenance_status_history", ["entity_type", "entity_id"])
    op.create_index("ix_maintenance_sh_changed_by", "maintenance_status_history", ["changed_by"])
    op.create_index("ix_maintenance_sh_created", "maintenance_status_history", ["created_at"])

    # ============================================================
    # AI CONVERSATIONS
    # ============================================================
    op.create_table(
        "ai_conversations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_conversations_user", "ai_conversations", ["user_id"])
    op.create_index("ix_ai_conversations_module", "ai_conversations", ["module"])
    op.create_index("ix_ai_conversations_user_module", "ai_conversations", ["user_id", "module"])

    # ============================================================
    # AI MESSAGES
    # ============================================================
    op.create_table(
        "ai_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_messages_conversation", "ai_messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("maintenance_status_history")
    op.drop_table("maintenance_costs")
    op.drop_table("maintenance_work_order_parts")
    op.drop_table("maintenance_plan_checklist")
    op.drop_table("maintenance_plans")
    op.drop_table("maintenance_interventions")
    op.drop_table("maintenance_intervenants")
    op.drop_table("maintenance_work_orders")
    op.drop_table("maintenance_requests")
    op.drop_table("maintenance_parts")
    op.drop_table("maintenance_contract_equipment")
    op.drop_table("maintenance_contracts")
    op.drop_table("maintenance_providers")
