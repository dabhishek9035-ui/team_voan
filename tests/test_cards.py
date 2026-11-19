"""
Unit tests for Reply Card Generator (PNG outputs, Localization, Forbidden Words guardrail).
"""

import io
from PIL import Image
from cards.generator import ReplyCardGenerator


def test_generate_ticket_received_card_en_and_kn():
    gen = ReplyCardGenerator()

    # English card with EXACT link badge
    card_en = gen.generate_ticket_received_card(
        language="en",
        link_type="EXACT",
        ticket_id="TKT-892104",
        origin_station="Indiranagar",
        destination_station="MG Road",
        fare=40.0,
    )
    assert card_en.size == (gen.CARD_WIDTH, gen.CARD_HEIGHT)
    png_bytes = gen.to_png_bytes(card_en)
    assert png_bytes.startswith(b"\x89PNG")

    # Kannada card with INFERRED link badge
    card_kn = gen.generate_ticket_received_card(
        language="kn",
        link_type="INFERRED",
        ticket_id="TKT-KN-102",
        origin_station="ಇಂದಿರಾನಗರ",
        destination_station="ಬೈಯಪ್ಪನಹಳ್ಳಿ",
        fare=30.0,
    )
    assert card_kn.size == (gen.CARD_WIDTH, gen.CARD_HEIGHT)


def test_generate_payment_missing_card():
    gen = ReplyCardGenerator()
    card = gen.generate_payment_missing_card(
        case_id="CASE-2026-9018",
        amount=50.0,
        utr="401999882211",
        language="en",
    )
    assert card.size == (gen.CARD_WIDTH, gen.CARD_HEIGHT)


def test_generate_needs_evidence_card():
    gen = ReplyCardGenerator()
    card = gen.generate_needs_evidence_card(
        requested_item="Bank SMS or UPI history",
        reason="UTR unreadable or missing from receipt",
        language="hi",
    )
    assert card.size == (gen.CARD_WIDTH, gen.CARD_HEIGHT)


def test_generate_could_not_read_and_processing_cards():
    gen = ReplyCardGenerator()
    c1 = gen.generate_could_not_read_card(language="en")
    c2 = gen.generate_processing_card(language="kn")
    assert c1.size == (gen.CARD_WIDTH, gen.CARD_HEIGHT)
    assert c2.size == (gen.CARD_WIDTH, gen.CARD_HEIGHT)


def test_forbidden_words_guardrail():
    gen = ReplyCardGenerator()
    # Ensure helper function cleans forbidden words
    dirty_text = "This claim was verified and no fraud was detected."
    cleaned = gen._sanitize_text(dirty_text)
    assert "fraud" not in cleaned.lower()
    assert "verified" not in cleaned.lower()
    assert "corroborated" in cleaned.lower()
