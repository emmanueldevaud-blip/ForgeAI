"""Import et normalisation des dépenses de l'Intendance.

L'empreinte est calculée sur toutes les colonnes métier importées : numéro de
demande, date, carte, libellé, quantité, unité, montant, société, centre de
coût, code comptable, libellé comptable et préparateur. Elle ne dépend donc
pas du seul numéro de demande et conserve deux lignes distinctes partageant
ce numéro.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any


EXCEL_HEADERS = {
    "A": "req_number",
    "B": "expense_date",
    "C": "bank_card",
    "D": "item_description",
    "E": "quantity",
    "F": "uom",
    "G": "amount",
    "H": "corporation",
    "I": "cost_center",
    "J": "account_description",
    "K": "prepared_by",
}


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        # Excel's 1900 date system; openpyxl normally performs this conversion,
        # but keeping it here makes the parser deterministic in tests too.
        return (date(1899, 12, 30) + timedelta(days=float(value)))
    text = normalize_text(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(" ", "").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _account_parts(value: Any) -> tuple[str | None, str | None]:
    text = normalize_text(value)
    if not text:
        return None, None
    code, separator, label = text.partition(" ")
    return code, normalize_text(label) if separator else None


def parse_excel_row(values: dict[str, Any], line_number: int) -> dict[str, Any]:
    account_code, account_label = _account_parts(values.get("J"))
    row = {
        "line_number": line_number,
        "req_number": int(values["A"]) if normalize_text(values.get("A")).isdigit() else None,
        "expense_date": normalize_date(values.get("B")),
        "bank_card": normalize_text(values.get("C")),
        "item_description": normalize_text(values.get("D")),
        "quantity": int(values["E"]) if normalize_text(values.get("E")).isdigit() else 1,
        "uom": normalize_text(values.get("F")) or None,
        "amount": normalize_decimal(values.get("G")),
        "corporation": int(values["H"]) if normalize_text(values.get("H")).isdigit() else None,
        "cost_center": int(values["I"]) if normalize_text(values.get("I")).isdigit() else None,
        "account_code": account_code,
        "account_label": account_label,
        "prepared_by": normalize_text(values.get("K")) or None,
    }
    invalid = []
    if row["req_number"] is None:
        invalid.append("numéro de demande")
    if row["expense_date"] is None:
        invalid.append("date")
    if not row["item_description"]:
        invalid.append("libellé")
    if row["amount"] is None:
        invalid.append("montant")
    row["invalid_reason"] = ", ".join(invalid) or None
    return row


def expense_fingerprint(row: dict[str, Any]) -> str:
    fields = (
        row.get("req_number"), row.get("expense_date"), row.get("bank_card"),
        row.get("item_description"), row.get("quantity"), row.get("uom"),
        row.get("amount"), row.get("corporation"), row.get("cost_center"),
        row.get("account_code"), row.get("account_label"), row.get("prepared_by"),
    )
    payload = "\x1f".join(normalize_text(v.isoformat() if isinstance(v, date) else v) for v in fields)
    return sha256(payload.encode("utf-8")).hexdigest()

