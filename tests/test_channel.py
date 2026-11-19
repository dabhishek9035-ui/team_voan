"""
Unit tests for Chat Channel Handler, RateLimiter, and Channel Integrations.
"""

import io
from PIL import Image
from intake.channel import ChannelHandler, RateLimiter
from intake.telegram_bot import TelegramChannelBot
from intake.whatsapp_webhook import process_twilio_request


def create_valid_png_bytes() -> bytes:
    img = Image.new("RGB", (200, 200), "#FFFFFF")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_rate_limiter():
    limiter = RateLimiter(max_requests=3, window_seconds=10.0)
    user = "user_123"
    assert limiter.is_allowed(user) is True
    assert limiter.is_allowed(user) is True
    assert limiter.is_allowed(user) is True
    # 4th request within window must be rejected
    assert limiter.is_allowed(user) is False


def test_channel_handler_validation_rejection():
    handler = ChannelHandler()

    # Reject non-image file
    invalid_bytes = b"This is a plain text file, not a PNG or JPG screenshot."
    res = handler.handle_incoming_screenshot(
        sender_id="sender_1",
        image_bytes=invalid_bytes,
    )
    assert res["status"] == "invalid_file"
    assert "not a readable image" in res["error"]


def test_channel_handler_join_code_mapping():
    handler = ChannelHandler()
    trip_id = handler.register_join_code("sender_test", "METRO2026")
    assert trip_id == "trip_bengaluru_fest_01"
    assert handler._sender_trip_map["sender_test"] == "trip_bengaluru_fest_01"


def test_channel_handler_screenshot_processing():
    handler = ChannelHandler()
    png_bytes = create_valid_png_bytes()

    # Test processing
    res = handler.handle_incoming_screenshot(
        sender_id="sender_regular",
        image_bytes=png_bytes,
        channel="telegram",
        caption="METRO2026",
    )
    assert res["status"] == "success"
    assert "evidence_id" in res
    assert "interp_id" in res
    assert res["processing_card_png"] is not None
    assert res["final_card_png"] is not None


def test_channel_adaptive_challenge():
    handler = ChannelHandler()
    card_bytes = handler.handle_adaptive_challenge(
        evidence_id="ev_test_88",
        requested_item="Bank SMS alert",
        reason="UTR unreadable on receipt",
        sender_id="sender_regular",
    )
    assert card_bytes.startswith(b"\x89PNG")


def test_telegram_bot_update_processor():
    bot = TelegramChannelBot()
    update = {
        "update_id": 1001,
        "message": {
            "chat": {"id": 987654},
            "caption": "/kn",
        },
    }
    res = bot.process_raw_telegram_update(update)
    assert res["status"] == "language_updated"
    assert res["lang"] == "kn"
