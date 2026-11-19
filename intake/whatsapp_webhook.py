"""
Twilio WhatsApp Sandbox Webhook Handler for Pratibimb Member A.
Secondary channel for WhatsApp users forwarding transit screenshots 1:1.
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import httpx
from fastapi import APIRouter, Form, Response

from intake.channel import ChannelHandler


router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])
_global_channel_handler: Optional[ChannelHandler] = None


def get_channel_handler() -> ChannelHandler:
    global _global_channel_handler
    if _global_channel_handler is None:
        _global_channel_handler = ChannelHandler()
    return _global_channel_handler


def process_twilio_request(
    from_number: str,
    body: Optional[str] = None,
    media_url: Optional[str] = None,
    media_content_type: Optional[str] = None,
    handler: Optional[ChannelHandler] = None,
) -> Dict[str, Any]:
    """
    Parses and executes a Twilio WhatsApp webhook payload.
    """
    ch = handler or get_channel_handler()
    sender_id = from_number.replace("whatsapp:", "").strip()

    if not media_url:
        return {
            "status": "text_only",
            "message": "Please send or forward a metro ticket or payment screenshot.",
        }

    # Fetch media bytes from Twilio MediaUrl
    try:
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(media_url)
            resp.raise_for_status()
            image_bytes = resp.content
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to download image from Twilio: {str(e)}",
        }

    return ch.handle_incoming_screenshot(
        sender_id=f"wa_{sender_id}",
        image_bytes=image_bytes,
        channel="whatsapp_sandbox",
        caption=body,
    )


@router.post("")
def twilio_whatsapp_webhook(
    From: str = Form(...),
    Body: Optional[str] = Form(None),
    NumMedia: int = Form(0),
    MediaUrl0: Optional[str] = Form(None),
    MediaContentType0: Optional[str] = Form(None),
):
    """
    Standard Twilio webhook endpoint responding with TwiML.
    """
    res = process_twilio_request(
        from_number=From,
        body=Body,
        media_url=MediaUrl0,
        media_content_type=MediaContentType0,
    )

    # Return standard TwiML XML response
    if res.get("status") == "success":
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            f"  <Message>Screenshot received and processed. Screenshot Type: {res.get('screenshot_type')}</Message>\n"
            "</Response>"
        )
    else:
        msg = res.get("error") or res.get("message") or "Received message."
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            "<Response>\n"
            f"  <Message>{msg}</Message>\n"
            "</Response>"
        )

    return Response(content=twiml, media_type="application/xml")
