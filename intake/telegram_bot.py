"""
Telegram Bot Interface for Pratibimb Member A.
Primary demo channel for live travellers sending transit screenshots.
Uses HTTP calls via httpx to the Telegram Bot API with polling support.
Includes a simulation/test mode when TELEGRAM_BOT_TOKEN is not configured.
"""

from __future__ import annotations
import os
import io
import sys
import time
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from PIL import Image
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
        caption = (message.get("caption", "") or message.get("text", "")).strip()

        # Check for start/help commands
        if caption.startswith(("/start", "/help")):
            welcome = (
                "Welcome to Pratibimb!\n"
                "Send any Namma Metro ticket QR, UPI payment receipt, bank SMS, or refund screenshot.\n"
                "Optional commands: /en (English), /kn (Kannada), /hi (Hindi).\n"
                "Include a join code (e.g. METRO2026) in your caption to link a trip."
            )
            if self.is_live:
                self.send_text(chat_id, welcome)
            return {"status": "help", "chat_id": chat_id, "message": welcome}

        # Check for language switch commands: /en, /kn, /hi
        if caption.startswith("/en"):
            self.channel_handler.set_sender_language(sender_id, "en")
            if self.is_live:
                self.send_text(chat_id, "Language set to English.")
            return {"status": "language_updated", "lang": "en", "chat_id": chat_id}
        elif caption.startswith("/kn"):
            self.channel_handler.set_sender_language(sender_id, "kn")
            if self.is_live:
                self.send_text(chat_id, "ಭಾಷೆಯನ್ನು ಕನ್ನಡಕ್ಕೆ ಬದಲಾಯಿಸಲಾಗಿದೆ.")
            return {"status": "language_updated", "lang": "kn", "chat_id": chat_id}
        elif caption.startswith("/hi"):
            self.channel_handler.set_sender_language(sender_id, "hi")
            if self.is_live:
                self.send_text(chat_id, "भाषा हिन्दी में सेट की गई है।")
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
            prompt = "Please send a metro ticket or payment screenshot to Pratibimb."
            if self.is_live:
                self.send_text(chat_id, prompt)
            return {
                "status": "text_only",
                "chat_id": chat_id,
                "message": prompt,
            }

        # Download image bytes from Telegram API (or mock in test mode)
        image_bytes = self._download_file(file_id)
        if not image_bytes:
            return {"status": "error", "error": "Could not download image from Telegram"}

        if self.is_live:
            self.send_text(chat_id, "Received, processing screenshot...")

        # Process through ChannelHandler
        result = self.channel_handler.handle_incoming_screenshot(
            sender_id=sender_id,
            image_bytes=image_bytes,
            channel="telegram",
            caption=caption,
        )
        result["chat_id"] = chat_id

        if self.is_live:
            if result.get("status") == "success" and result.get("final_card_png"):
                reply_caption = (
                    f"Type: {result.get('screenshot_type')} "
                    f"| Evidence: {result.get('evidence_id')}"
                )
                self.send_card(chat_id, result["final_card_png"], caption=reply_caption)
            elif result.get("error"):
                self.send_text(chat_id, result["error"])

        return result

    def _download_file(self, file_id: str) -> Optional[bytes]:
        """Downloads file bytes via Telegram getFile API, with mock fallback."""
        if not self.is_live:
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

    def send_text(self, chat_id: str, text: str) -> bool:
        """Sends a text message back to user's Telegram chat."""
        if not self.is_live:
            return True
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    f"{self.API_BASE}{self.bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                )
                return res.status_code == 200
        except Exception:
            return False

    def send_card(self, chat_id: str, card_png_bytes: bytes, caption: Optional[str] = None) -> bool:
        """Sends reply card PNG back to user's Telegram chat."""
        if not self.is_live:
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

    def get_me(self) -> Dict[str, Any]:
        """Verifies the Telegram bot token via getMe."""
        if not self.is_live:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not set in environment or .env")
        with httpx.Client(timeout=10.0) as client:
            res = client.get(f"{self.API_BASE}{self.bot_token}/getMe")
            res.raise_for_status()
            return res.json()

    def run_polling(self, poll_interval: float = 1.0) -> None:
        """Long-polls Telegram Bot API getUpdates and routes incoming screenshots to Member B."""
        with httpx.Client(timeout=10.0) as client:
            client.post(f"{self.API_BASE}{self.bot_token}/deleteWebhook", json={"drop_pending_updates": False})
        me = self.get_me()
        username = me.get("result", {}).get("username", "unknown_bot")
        core_url = self.channel_handler.store_client.base_url
        print(f"Telegram bot @{username} connected and polling (Core API: {core_url})", flush=True)

        while True:
            try:
                with httpx.Client(timeout=30.0) as client:
                    res = client.get(
                        f"{self.API_BASE}{self.bot_token}/getUpdates",
                        params={"offset": self.last_update_id + 1, "timeout": 20},
                    )
                    res.raise_for_status()
                    updates = res.json().get("result", [])
                for upd in updates:
                    self.last_update_id = max(self.last_update_id, int(upd["update_id"]))
                    outcome = self.process_raw_telegram_update(upd)
                    if outcome:
                        print(
                            f"[telegram] update={upd['update_id']} status={outcome.get('status')} "
                            f"type={outcome.get('screenshot_type', '-')} ev={outcome.get('evidence_id', '-')}",
                            flush=True,
                        )
            except KeyboardInterrupt:
                print("Telegram polling stopped.", flush=True)
                break
            except Exception as exc:
                print(f"[telegram] polling error: {exc}", flush=True)
                time.sleep(poll_interval)


if __name__ == "__main__":
    TelegramChannelBot().run_polling()
