"""
Unit tests for Extraction Pipeline Service (Evidence + Interpretation production).
"""

import io
from PIL import Image
from intake.models import ScreenshotType
from extraction.service import ExtractionService


def create_test_image_bytes(text_lines: list) -> bytes:
    img = Image.new("RGB", (500, 300), "#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_process_screenshot_pipeline():
    service = ExtractionService()

    # Provide simulated OCR text for the test
    test_text = (
        "Namma Metro WhatsApp Ticketing\n"
        "Single Journey Ticket\n"
        "Ticket ID: TKT-108920\n"
        "From: Indiranagar\n"
        "To: MG Road\n"
        "Fare: Rs. 40.00\n"
        "Status: Valid\n"
    )
    service.sarvam_client._simulate_digitise = lambda _: (test_text, "en")
    service.qr_decoder.decode = lambda _: (
        "BMRCL|TKT-108920|INDIRANAGAR|MG_ROAD|40.00|2026-11-19",
        {
            "operator": "BMRCL",
            "ticket_id": "TKT-108920",
            "origin_station": "INDIRANAGAR",
            "destination_station": "MG_ROAD",
            "fare": 40.0,
        },
        True,
    )

    img_bytes = create_test_image_bytes([])
    evidence, interpretation = service.process_screenshot(
        image_path_or_bytes=img_bytes,
        sender_id="traveller_meera",
        channel="telegram",
        trip_id="trip_fest_01",
    )

    # Validate Evidence
    assert evidence.sender_id == "traveller_meera"
    assert evidence.channel == "telegram"
    assert len(evidence.sha256) == 64
    assert len(evidence.phash) == 16

    # Validate Interpretation
    assert interpretation.screenshot_type == ScreenshotType.TICKET_QR
    assert interpretation.type_confidence >= 0.85
    assert interpretation.fields.amount == 40.0
    assert interpretation.fields.ticket_id == "TKT-108920"
    assert interpretation.fields.qr_payload_parseable is True

    # Validate Field Confidences and Sources
    assert interpretation.field_confidence["amount"] > 0.8
    assert interpretation.field_sources["ticket_id"] == "qr_decoder"
    assert interpretation.field_sources["amount"] in ["sarvam_digitise", "qr_decoder"]


def test_hallucination_guardrail():
    # If OCR text does not contain a value, it must be null with confidence 0.0
    from extraction.sarvam_client import SarvamClient

    fields = {
        "amount": 40.0,
        "utr": "401928374615",  # NOT in text!
        "ticket_id": "TKT-9912",  # Present in text
    }
    confidences = {"amount": 0.9, "utr": 0.9, "ticket_id": 0.9}
    raw_text = "Ticket ID: TKT-9912. Total fare: Rs 40.00"

    validated_fields, validated_conf = SarvamClient.validate_hallucinations(
        fields, confidences, raw_text
    )

    # Amount & Ticket ID should remain
    assert validated_fields["amount"] == 40.0
    assert validated_fields["ticket_id"] == "TKT-9912"

    # UTR was invented (not in text) -> MUST BE NULL
    assert validated_fields["utr"] is None
    assert validated_conf["utr"] == 0.0
