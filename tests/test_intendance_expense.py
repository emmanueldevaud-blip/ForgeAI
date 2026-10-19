from datetime import date
from decimal import Decimal

from app.services.intendance_expense import expense_fingerprint, parse_excel_row


def row(**overrides):
    value = {
        "A": "70342", "B": 45585, "C": "(3121424) CB E. Devaud",
        "D": " Achat test ", "E": "1", "F": "U", "G": "17.579999999",
        "H": "279", "I": "333", "J": "606810-1-333-0279 Achats non stockés",
        "K": "Matthieu BLANCHARD",
    }
    value.update(overrides)
    return value


def test_parse_excel_row_normalizes_excel_values():
    parsed = parse_excel_row(row(), 2)
    assert parsed["expense_date"] == date(2024, 10, 20)
    assert parsed["amount"] == Decimal("17.58")
    assert parsed["account_code"] == "606810-1-333-0279"
    assert parsed["item_description"] == "Achat test"
    assert parsed["invalid_reason"] is None


def test_fingerprint_keeps_same_request_number_for_distinct_expenses():
    first = parse_excel_row(row(D="Article A"), 2)
    second = parse_excel_row(row(D="Article B"), 3)
    assert first["req_number"] == second["req_number"]
    assert expense_fingerprint(first) != expense_fingerprint(second)


def test_invalid_row_is_explicit():
    parsed = parse_excel_row(row(A="", B="", D="", G="not-a-number"), 8)
    assert parsed["invalid_reason"] == "numéro de demande, date, libellé, montant"
