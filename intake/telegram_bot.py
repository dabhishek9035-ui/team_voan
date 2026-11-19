"""
Telegram Bot Interface for Pratibimb Member A.
Primary demo channel for live travellers sending transit screenshots.
Uses direct asynchronous HTTP calls via httpx to the Telegram Bot API.
Includes a simulation/test mode when TELEGRAM_BOT_TOKEN is not configured.
"""

from __future__ import annotations
import os
import io
from typing import Optional, Dict, Any, List
import httpx
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

from intake.channel import ChannelHandler


class TelegramChannelBot:
    """
    Manages Telegram bot interaction for Pratibimb screenshots.
    """

    API_BASE = "https://api.telegram.org/bot"

    def __init__(
        self,
        bot_token: Optional[str] = None,
        channel_handler: Optional[ChannelHandler] = None,
    ):
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.channel_handler = channel_handler or ChannelHandler()
        self.is_live = bool(self.bot_token)
        self.last_update_id = 0

    def process_raw_telegram_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parses a Telegram webhook or polling update object.
        Extracts sender, photos/documents, captions, and forwards to ChannelHandler.
        """
        message = update.get("message") or update.get("channel_post")
        if not message:
            return None

        chat_id = str(message.get("chat", {}).get("id"))
        sender_id = f"tg_{chat_id}"
        caption = message.get("caption", "") or message.get("text", "")

        # Check for language switch commands: /en, /kn, /hi
        if caption.startswith("/en"):
            self.channel_handler.set_sender_language(sender_id, "en")
            return {"status": "language_updated", "lang": "en", "chat_id": chat_id}
        elif caption.startswith("/kn"):
            self.channel_handler.set_sender_language(sender_id, "kn")
            return {"status": "language_updated", "lang": "kn", "chat_id": chat_id}
        elif caption.startswith("/hi"):
            self.channel_handler.set_sender_language(sender_id, "hi")
            return {"status": "language_updated", "lang": "hi", "chat_id": chat_id}

        # Check for photo array (Telegram sends multiple resolutions; highest is last)
        photo_arr = message.get("photo")
        doc = message.get("document")

        file_id = None
        if photo_arr and len(photo_arr) > 0:
            file_id = photo_arr[-1].get("file_id")
        elif doc and doc.get("mime_type", "").startswith("image/"):
            file_id = doc.get("file_id")

        if not file_id:
            # Message without an image
            return {
                "status": "text_only",
                "chat_id": chat_id,
                "message": "Please send a metro ticket or payment screenshot to Pratibimb.",
            }

        # Download image bytes from Telegram API (or mock in test mode)
        image_bytes = self._download_file(file_id)
        if not image_bytes:
            return {"status": "error", "error": "Could not download image from Telegram"}

        # Process through ChannelHandler
        result = self.channel_handler.handle_incoming_screenshot(
            sender_id=sender_id,
            image_bytes=image_bytes,
            channel="telegram",
            caption=caption,
        )
        result["chat_id"] = chat_id
        return result

    def _download_file(self, file_id: str) -> Optional[bytes]:
        """Downloads file bytes via Telegram getFile API, with mock fallback."""
        if not self.is_live:
            # In simulation mode, generate a synthetic PNG ticket for testing
            img = Image.new("RGB", (300, 300), "#FFFFFF")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.get(f"{self.API_BASE}{self.bot_token}/getFile?file_id={file_id}")
                res.raise_for_status()
                file_path = res.json().get("result", {}).get("file_path")
                if not file_path:
                    return None
                file_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
                dl_res = client.get(file_url)
                dl_res.raise_for_status()
                return dl_res.content
        except Exception:
            return None

    def send_card(self, chat_id: str, card_png_bytes: bytes, caption: Optional[str] = None) -> bool:
        """Sends reply card PNG back to user's Telegram chat."""
        if not self.is_live:
            # Simulated send
            return True

        try:
            with httpx.Client(timeout=15.0) as client:
                files = {"photo": ("card.png", card_png_bytes, "image/png")}
                data = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption
                res = client.post(
                    f"{self.API_BASE}{self.bot_token}/sendPhoto",
                    data=data,
                    files=files,
                )
                return res.status_code == 200
        except Exception:
            return False
