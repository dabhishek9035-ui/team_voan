"""
Unit tests for Normalisers (Amounts, Indian Dates/Times, Kannada Numerals, UTR OCR Cleaning).
"""

from intake.normalisers import (
    translate_kannada_numerals,
    normalize_amount,
    normalize_timestamp,
    normalize_utr,
    normalize_order_or_ticket_id,
    mask_payer_name,
)


def test_kannada_numeral_translation():
    assert translate_kannada_numerals("೪೦") == "40"
    assert translate_kannada_numerals("₹ ೩೫.೫೦") == "₹ 35.50"
    assert translate_kannada_numerals("೦೧೨೩೪೫೬೭೮೯") == "0123456789"


def test_normalize_amount():
    amt, curr = normalize_amount("₹ 40.00")
    assert amt == 40.0
    assert curr == "INR"

    amt, curr = normalize_amount("Rs. 1,250.50")
    assert amt == 1250.5
    assert curr == "INR"

    amt, curr = normalize_amount("₹೪೦")
    assert amt == 40.0
    assert curr == "INR"

    amt, curr = normalize_amount(35)
    assert amt == 35.0

    amt, curr = normalize_amount(None)
    assert amt is None
    assert curr is None


def test_normalize_timestamp():
    # ISO string
    ts = normalize_timestamp("2026-11-19T10:14:00")
    assert ts == "2026-11-19T10:14:00"

    # Indian DD/MM/YYYY format with 12h time
    ts = normalize_timestamp("19/11/2026 10:14 AM")
    assert ts == "2026-11-19T10:14:00"

    # With Kannada digits
    ts = normalize_timestamp("೧೯/೧೧/೨೦೨೬ ೧೦:೧೪ AM")
    assert ts == "2026-11-19T10:14:00"


def test_normalize_utr_and_ocr_corrections():
    # Perfect 12-digit UTR
    utr, corr = normalize_utr("401928374615")
    assert utr == "401928374615"
    assert len(corr) == 0

    # Common OCR confusion: letter 'O' instead of '0', letter 'I' instead of '1'
    utr_dirty = "4OI9283746IO"
    utr_clean, corr = normalize_utr(utr_dirty)
    assert utr_clean == "401928374610"
    assert len(corr) > 0
    assert corr[0]["rule"] == "ocr_digit_confusion_substitution"

    # With label prefix
    utr, corr = normalize_utr("UPI Ref No: 401928374615")
    assert utr == "401928374615"


def test_normalize_order_or_ticket_id():
    tkt, corr = normalize_order_or_ticket_id("Ticket ID: TKT-108920", id_type="ticket_id")
    assert tkt == "TKT-108920"
    assert len(corr) > 0

    ord_id, corr = normalize_order_or_ticket_id("Order ID: ORD-99182", id_type="order_id")
    assert ord_id == "ORD-99182"


def test_mask_payer_name():
    assert mask_payer_name("Rahul Sharma") == "R***l S****a"
    assert mask_payer_name("Meera") == "M***a"
    assert mask_payer_name(None) is None
