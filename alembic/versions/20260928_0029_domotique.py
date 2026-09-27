"""Add domotique tables (devices, sensors, readings, outputs, profiles, phases, cycles, events)

Revision ID: 20260928_0029
Revision ID Note: Module Domotique — sechoir a saucisson (Raspberry Pi passerelle)

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260928_0029"
down_revision = "20260927_0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domotique_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False, server_default="dryer"),
        sa.Column("base_url", sa.String(300), nullable=True),
        sa.Column("poll_interval_s", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_devices_code", "domotique_devices", ["code"], unique=True)

    op.create_table(
        "domotique_sensors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("current_value", sa.Float(), nullable=True),
        sa.Column("current_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["domotique_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "key", name="uq_domotique_sensor_key"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_sensors_device_id", "domotique_sensors", ["device_id"])

    op.create_table(
        "domotique_sensor_readings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sensor_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["sensor_id"], ["domotique_sensors.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_sensor_readings_sensor_id", "domotique_sensor_readings", ["sensor_id"])
    op.create_index("ix_domotique_readings_sensor_recorded", "domotique_sensor_readings", ["sensor_id", "recorded_at"])

    op.create_table(
        "domotique_outputs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(30), nullable=False, server_default="other"),
        sa.Column("mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("state", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["domotique_devices.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_id", "index", name="uq_domotique_output_index"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_outputs_device_id", "domotique_outputs", ["device_id"])

    op.create_table(
        "domotique_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_weight_loss_pct", sa.Float(), nullable=True),
        sa.Column("weight_loss_min_pct", sa.Float(), nullable=True),
        sa.Column("weight_loss_max_pct", sa.Float(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_profiles_code", "domotique_profiles", ["code"], unique=True)

    op.create_table(
        "domotique_phases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("target_temperature", sa.Float(), nullable=True),
        sa.Column("target_humidity", sa.Float(), nullable=True),
        sa.Column("tolerance_temperature", sa.Float(), nullable=True),
        sa.Column("tolerance_humidity", sa.Float(), nullable=True),
        sa.Column("min_duration_hours", sa.Float(), nullable=True),
        sa.Column("max_duration_hours", sa.Float(), nullable=True),
        sa.Column("weight_loss_target_pct", sa.Float(), nullable=True),
        sa.Column("exit_condition", sa.String(10), nullable=False, server_default="time"),
        sa.ForeignKeyConstraint(["profile_id"], ["domotique_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "order", name="uq_domotique_phase_order"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_phases_profile_id", "domotique_phases", ["profile_id"])

    op.create_table(
        "domotique_cycles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(150), nullable=True),
        sa.Column("product", sa.String(100), nullable=True),
        sa.Column("casing_size", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="preparing"),
        sa.Column("current_phase_id", sa.Integer(), nullable=True),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initial_weight", sa.Float(), nullable=True),
        sa.Column("current_weight", sa.Float(), nullable=True),
        sa.Column("target_weight_loss_pct", sa.Float(), nullable=True),
        sa.Column("manual_outputs", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["domotique_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["domotique_profiles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["current_phase_id"], ["domotique_phases.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_cycles_device_id", "domotique_cycles", ["device_id"])
    op.create_index("ix_domotique_cycles_profile_id", "domotique_cycles", ["profile_id"])
    op.create_index("ix_domotique_cycles_status", "domotique_cycles", ["status"])

    op.create_table(
        "domotique_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("cycle_id", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["domotique_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cycle_id"], ["domotique_cycles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_unicode_ci",
    )
    op.create_index("ix_domotique_events_device_id", "domotique_events", ["device_id"])
    op.create_index("ix_domotique_events_device_created", "domotique_events", ["device_id", "created_at"])
    op.create_index("ix_domotique_events_cycle_created", "domotique_events", ["cycle_id", "created_at"])


def downgrade() -> None:
    op.drop_table("domotique_events")
    op.drop_table("domotique_cycles")
    op.drop_table("domotique_phases")
    op.drop_table("domotique_profiles")
    op.drop_table("domotique_outputs")
    op.drop_table("domotique_sensor_readings")
    op.drop_table("domotique_sensors")
    op.drop_table("domotique_devices")
