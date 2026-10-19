"""Ajoute le suivi des dépenses de l'Intendance.

Les données importées sont conservées dans des tables dédiées. Les valeurs
initiales des sites et alias sont des référentiels fonctionnels explicites;
aucune catégorie comptable n'est déduite ici.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261019_0002"
down_revision = "20261019_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intendance_sites",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_intendance_sites_name", "intendance_sites", ["name"])

    op.create_table(
        "intendance_card_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("user_name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("alias"),
    )
    op.create_index("ix_intendance_card_aliases_alias", "intendance_card_aliases", ["alias"])

    op.create_table(
        "intendance_account_codes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_intendance_account_codes_code", "intendance_account_codes", ["code"])
    op.create_index("ix_intendance_account_codes_category", "intendance_account_codes", ["category"])

    op.create_table(
        "intendance_import_batches",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reference", sa.String(64), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="analyzed"),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicate_existing", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_duplicate_in_file", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_unknown_codes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_unknown_users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_invalid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_count", sa.Integer(), nullable=True),
        sa.UniqueConstraint("reference"),
    )
    op.create_index("ix_intendance_import_batches_reference", "intendance_import_batches", ["reference"])

    op.create_table(
        "intendance_expenses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("req_number", sa.Integer(), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("bank_card", sa.String(255), nullable=False, server_default=""),
        sa.Column("item_description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uom", sa.String(16), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("corporation", sa.Integer(), nullable=True),
        sa.Column("cost_center", sa.Integer(), nullable=True),
        sa.Column("account_code", sa.String(80), nullable=True),
        sa.Column("account_label", sa.Text(), nullable=True),
        sa.Column("prepared_by", sa.String(255), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("category_is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_name", sa.String(100), nullable=True),
        sa.Column("user_is_manual", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("intendance_sites.id", ondelete="SET NULL"), nullable=True),
        sa.Column("import_batch_id", sa.Integer(), sa.ForeignKey("intendance_import_batches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("fingerprint"),
    )
    for name, columns in {
        "ix_intendance_expenses_fingerprint": ["fingerprint"],
        "ix_intendance_expenses_req_number": ["req_number"],
        "ix_intendance_expenses_expense_date": ["expense_date"],
        "ix_intendance_expenses_account_code": ["account_code"],
        "ix_intendance_expenses_category": ["category"],
        "ix_intendance_expenses_user_name": ["user_name"],
        "ix_intendance_expenses_site_id": ["site_id"],
        "ix_intendance_expenses_import_batch_id": ["import_batch_id"],
    }.items():
        op.create_index(name, "intendance_expenses", columns)

    op.create_table(
        "intendance_import_staged_rows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.Integer(), sa.ForeignKey("intendance_import_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("req_number", sa.Integer(), nullable=True),
        sa.Column("expense_date", sa.Date(), nullable=True),
        sa.Column("bank_card", sa.String(255), nullable=False, server_default=""),
        sa.Column("item_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uom", sa.String(16), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("corporation", sa.Integer(), nullable=True),
        sa.Column("cost_center", sa.Integer(), nullable=True),
        sa.Column("account_code", sa.String(80), nullable=True),
        sa.Column("account_label", sa.Text(), nullable=True),
        sa.Column("prepared_by", sa.String(255), nullable=True),
        sa.Column("invalid_reason", sa.String(120), nullable=True),
        sa.Column("is_duplicate_existing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_duplicate_in_file", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_intendance_import_staged_rows_batch_id", "intendance_import_staged_rows", ["batch_id"])
    op.create_index("ix_intendance_import_staged_rows_fingerprint", "intendance_import_staged_rows", ["fingerprint"])

    op.create_table(
        "intendance_expense_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("expense_id", sa.Integer(), sa.ForeignKey("intendance_expenses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(50), nullable=False),
        sa.Column("old_value", sa.String(255), nullable=True),
        sa.Column("new_value", sa.String(255), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_intendance_expense_history_expense_id", "intendance_expense_history", ["expense_id"])

    conn = op.get_bind()
    sites = [
        "APPARTEMENTS RIOM TOULON APPT1", "APPARTEMENTS RIOM TOULON APPT2", "APPARTEMENTS RIOM TOULON APPT3",
        "APPARTEMENT CLERMONT MOUCHET", "APPARTEMENT CLERMONT PUY", "APPARTEMENT CEBAZAT SOUVILLE",
        "APPARTEMENT RIOM MARENGO 1", "APPARTEMENT RIOM MARENGO 2", "COMMUN RIOM/CEBAZAT",
        "COMMUN APPARTEMENTS", "CEBAZAT", "RIOM", "PUTEAUX", "DEPLACEMENTS", "JPO",
    ]
    conn.execute(sa.text("INSERT INTO intendance_sites (name, sort_order) VALUES (:name, :sort_order)"), [{"name": n, "sort_order": i} for i, n in enumerate(sites)])
    aliases = {
        "(3013389) CB Le Gall S.": "LE GALL", "(3031084) CB Rosello M.": "ROSELLO",
        "(3121424) CB E. Devaud": "DEVAUD", "(3031534) CB Partel C.": "PARTEL",
        "(3019418) CB Berthoud M.": "BERTHOUD", "PUNCHOUT/HUB": "HUB",
    }
    conn.execute(sa.text("INSERT INTO intendance_card_aliases (alias, user_name) VALUES (:alias, :user_name)"), [{"alias": a, "user_name": u} for a, u in aliases.items()])


def downgrade() -> None:
    op.drop_table("intendance_expense_history")
    op.drop_table("intendance_import_staged_rows")
    op.drop_table("intendance_expenses")
    op.drop_table("intendance_import_batches")
    op.drop_table("intendance_account_codes")
    op.drop_table("intendance_card_aliases")
    op.drop_table("intendance_sites")
