"""
Unit tests for Local QR Code Decoder (OpenCV multi-pass, payload parser).
"""

import io
import qrcode
from PIL import Image
from intake.qr_decoder import QRDecoder


def generate_qr_image(payload: str) -> Image.Image:
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB")


def test_qr_decode_bmrcl_structured_payload():
    payload = "BMRCL|TKT-892104|INDIRANAGAR|MG_ROAD|40.00|2026-11-19T23:59:59"
    img = generate_qr_image(payload)

    decoder = QRDecoder()
    raw, parsed, parseable = decoder.decode(img)

    assert raw == payload
    assert parseable is True
    assert isinstance(parsed, dict)
    assert parsed["operator"] == "BMRCL"
    assert parsed["ticket_id"] == "TKT-892104"
    assert parsed["origin_station"] == "INDIRANAGAR"
    assert parsed["destination_station"] == "MG ROAD"
    assert parsed["fare"] == 40.0


def test_qr_decode_json_payload():
    json_str = '{"ticket_id": "TKT-9912", "amount": 30.0, "status": "active"}'
    img = generate_qr_image(json_str)

    decoder = QRDecoder()
    raw, parsed, parseable = decoder.decode(img)

    assert raw == json_str
    assert parseable is True
    assert parsed["ticket_id"] == "TKT-9912"
    assert parsed["amount"] == 30.0


def test_qr_decode_opaque_payload():
    # Opaque cryptographic signature or token
    opaque = "MEYCIQDx93kaL3/9zKp8+s71jN2...base64opaque"
    img = generate_qr_image(opaque)

    decoder = QRDecoder()
    raw, parsed, parseable = decoder.decode(img)

    assert raw == opaque
    assert parseable is False
    assert parsed is None


def test_no_qr_code():
    blank = Image.new("RGB", (300, 300), "#FFFFFF")
    decoder = QRDecoder()
    raw, parsed, parseable = decoder.decode(blank)
    assert raw is None
    assert parsed is None
    assert parseable is False
