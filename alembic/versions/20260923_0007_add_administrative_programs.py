"""Add configurable administrative volunteer programs."""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0007"
down_revision = "20260923_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "administrative_capabilities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
         sa.Column("description", sa.Text(), nullable=True),
         sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("code"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "administrative_volunteer_capabilities",
        sa.Column("volunteer_id", sa.Integer(), nullable=False),
        sa.Column("capability_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["capability_id"], ["administrative_capabilities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("volunteer_id", "capability_id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "administrative_volunteer_unavailabilities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("volunteer_id", sa.Integer(), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_administrative_unavailability_volunteer", "administrative_volunteer_unavailabilities", ["volunteer_id"])
    op.create_table(
        "administrative_program_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
         sa.Column("description", sa.Text(), nullable=True),
         sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
         sa.Column("frequency", sa.String(20), nullable=False, server_default="weekly"),
         sa.Column("weekday", sa.Integer(), nullable=False, server_default="0"),
         sa.Column("interval", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("code"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_table(
        "administrative_role_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("program_type_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("required_capability_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_optional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(["program_type_id"], ["administrative_program_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["required_capability_id"], ["administrative_capabilities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("program_type_id", "code", name="uq_administrative_role_type_code"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_administrative_role_type_program", "administrative_role_types", ["program_type_id"])
    op.create_table(
        "administrative_monthly_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("program_type_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False), sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["program_type_id"], ["administrative_program_types.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("program_type_id", "year", "month", name="uq_administrative_session_month"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_administrative_session_program", "administrative_monthly_sessions", ["program_type_id"])
    op.create_table(
        "administrative_assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False), sa.Column("role_type_id", sa.Integer(), nullable=False),
        sa.Column("volunteer_id", sa.Integer(), nullable=False), sa.Column("scheduled_date", sa.Date(), nullable=False), sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["administrative_monthly_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_type_id"], ["administrative_role_types.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["volunteer_id"], ["volunteers.id"], ondelete="RESTRICT"),
         sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("session_id", "role_type_id", "scheduled_date", name="uq_administrative_assignment_role_date"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_administrative_assignment_session", "administrative_assignments", ["session_id"])
    op.create_index("ix_administrative_assignment_volunteer", "administrative_assignments", ["volunteer_id"])

    capabilities = (
        ("worship_president", "Président du culte"), ("worship_prayer", "Prière"),
        ("worship_reader", "Lecteur texte du jour et Bible"), ("worship_commentary", "Commentaire"),
        ("training_president", "Président formation"), ("spiritual_thought", "Pensée spirituelle"),
        ("training", "Formation"), ("weekly_riom", "Responsable semaine Riom"),
        ("weekly_cebazat", "Responsable semaine Cébazat"), ("worship_broadcast", "Diffusion du culte"),
    )
    for code, name in capabilities:
        op.execute(sa.text("INSERT INTO administrative_capabilities (code, name) SELECT :code, :name WHERE NOT EXISTS (SELECT 1 FROM administrative_capabilities WHERE code = :code)").bindparams(code=code, name=name))

    programs = (
        ("worship", "Culte", "weekly", 0, 1),
        ("training", "Formation", "weekly", 0, 2),
        ("weekly_leaders", "Responsables de semaine", "weekly", 0, 1),
    )
    for code, name, frequency, weekday, interval in programs:
        op.execute(sa.text("INSERT INTO administrative_program_types (code, name, frequency, weekday, `interval`) SELECT :code, :name, :frequency, :weekday, :interval WHERE NOT EXISTS (SELECT 1 FROM administrative_program_types WHERE code = :code)").bindparams(code=code, name=name, frequency=frequency, weekday=weekday, interval=interval))
    roles = (
        ("worship", "president", "Président", "worship_president", False), ("worship", "prayer", "Prière", "worship_prayer", False),
        ("worship", "reader", "Lecteur", "worship_reader", False), ("worship", "commentary_1", "Commentaire 1", "worship_commentary", False),
        ("worship", "commentary_2", "Commentaire 2", "worship_commentary", False), ("worship", "commentary_3", "Commentaire 3", "worship_commentary", False),
        ("training", "president", "Président", "training_president", False), ("training", "prayer", "Prière", "worship_prayer", False),
        ("training", "thought", "Pensée", "spiritual_thought", False), ("training", "training", "Formation", "training", False),
        ("training", "extra_part", "Partie supplémentaire", "training", True),
        ("weekly_leaders", "riom", "Riom", "weekly_riom", False), ("weekly_leaders", "cebazat", "Cébazat", "weekly_cebazat", False),
        ("weekly_leaders", "broadcast", "Diffusion", "worship_broadcast", False),
    )
    for program_code, code, name, capability_code, is_optional in roles:
        op.execute(sa.text("INSERT INTO administrative_role_types (program_type_id, code, name, required_capability_id, is_optional) SELECT p.id, :code, :name, c.id, :is_optional FROM administrative_program_types p JOIN administrative_capabilities c ON c.code = :capability_code WHERE p.code = :program_code AND NOT EXISTS (SELECT 1 FROM administrative_role_types r WHERE r.program_type_id = p.id AND r.code = :code)").bindparams(program_code=program_code, code=code, name=name, capability_code=capability_code, is_optional=is_optional))


def downgrade() -> None:
    op.drop_index("ix_administrative_assignment_volunteer", table_name="administrative_assignments")
    op.drop_index("ix_administrative_assignment_session", table_name="administrative_assignments")
    op.drop_table("administrative_assignments")
    op.drop_index("ix_administrative_session_program", table_name="administrative_monthly_sessions")
    op.drop_table("administrative_monthly_sessions")
    op.drop_index("ix_administrative_role_type_program", table_name="administrative_role_types")
    op.drop_table("administrative_role_types")
    op.drop_table("administrative_program_types")
    op.drop_index("ix_administrative_unavailability_volunteer", table_name="administrative_volunteer_unavailabilities")
    op.drop_table("administrative_volunteer_unavailabilities")
    op.drop_table("administrative_volunteer_capabilities")
    op.drop_table("administrative_capabilities")
