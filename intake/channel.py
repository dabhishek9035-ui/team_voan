"""
Chat Channel Handler for Pratibimb Member A.
Manages intake logic across Telegram bot and Twilio WhatsApp sandbox.

Capabilities:
1. Rate limiting (per-sender window) and size limit enforcement (max 15MB).
2. Polite rejection of non-image uploads.
3. Multi-image message handling.
4. One-time coordinator join-code mapping to trip_id.
5. Immediate 'Processing' acknowledgement card.
6. Execution of ExtractionService pipeline and storage in Member B's store.
7. Reply card generation in traveller's preferred language.
8. Adaptive evidence challenge handler for Member B's POST /challenge/{id}.
"""

from __future__ import annotations
import time
import io
from pathlib import Path
from typing import Optional, Dict, Any, List, Union, Tuple
from PIL import Image

from intake.models import ScreenshotType, EvidenceRecord, InterpretationRecord
from intake.store_client import StoreClient
from extraction.service import ExtractionService
from cards.generator import ReplyCardGenerator


class RateLimiter:
    """Sliding-window rate limiter per sender."""

    def __init__(self, max_requests: int = 10, window_seconds: float = 60.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = {}

    def is_allowed(self, sender_id: str) -> bool:
        now = time.time()
        timestamps = self._requests.setdefault(sender_id, [])
        # Prune old timestamps outside the window
        valid = [t for t in timestamps if now - t < self.window_seconds]
        self._requests[sender_id] = valid

        if len(valid) >= self.max_requests:
            return False
        valid.append(now)
        return True


class ChannelHandler:
    """
    Core intake channel coordinator.
    """

    MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB

    def __init__(
        self,
        extraction_service: Optional[ExtractionService] = None,
        store_client: Optional[StoreClient] = None,
        card_generator: Optional[ReplyCardGenerator] = None,
    ):
        self.extraction_service = extraction_service or ExtractionService()
        self.store_client = store_client or StoreClient()
        self.card_generator = card_generator or ReplyCardGenerator()
        self.rate_limiter = RateLimiter(max_requests=10, window_seconds=60.0)

        # Mapping sender_id -> trip_id
        self._sender_trip_map: Dict[str, str] = {}
        # Mapping sender_id -> preferred language ('en', 'kn', 'hi')
        self._sender_language_map: Dict[str, str] = {}

    def set_sender_language(self, sender_id: str, language_code: str) -> None:
        """Sets sender language preference."""
        if language_code in ["en", "kn", "hi"]:
            self._sender_language_map[sender_id] = language_code

    def get_sender_language(self, sender_id: str) -> str:
        """Retrieves language preference, default English."""
        return self._sender_language_map.get(sender_id, "en")

    def register_join_code(self, sender_id: str, join_code: str) -> Optional[str]:
        """Maps a traveller to a trip using a one-time join code."""
        trip_id = self.store_client.lookup_trip_by_join_code(join_code)
        if trip_id:
            self._sender_trip_map[sender_id] = trip_id
            return trip_id
        return None

    def validate_upload(
        self,
        image_bytes: bytes,
        mime_type: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validates upload file size and image integrity.
        Rejects non-images or oversized files politely.
        """
        if len(image_bytes) > self.MAX_FILE_SIZE_BYTES:
            return False, "File exceeds maximum size of 15MB. Please send a standard screenshot."

        # Verify PIL can open the image
        try:
            with Image.open(io.BytesIO(image_bytes)) as img:
                img.verify()
        except Exception:
            return False, "The file provided is not a readable image. Pratibimb only accepts screenshots (PNG, JPG, WEBP)."

        return True, None

    def handle_incoming_screenshot(
        self,
        sender_id: str,
        image_bytes: bytes,
        channel: str = "telegram",
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Processes an incoming screenshot message from Telegram or WhatsApp.
        Returns:
            {
                "status": "success" | "rate_limited" | "invalid_file",
                "processing_card_png": bytes,
                "final_card_png": bytes,
                "evidence_id": str,
                "interp_id": str,
                "screenshot_type": str,
                "message_text": str
            }
        """
        # 1. Rate limiting check
        if not self.rate_limiter.is_allowed(sender_id):
            return {
                "status": "rate_limited",
                "error": "Rate limit reached. Please wait a minute before sending more screenshots.",
                "processing_card_png": None,
                "final_card_png": None,
            }

        # 2. Check for join code in caption if user hasn't joined a trip yet
        trip_id = self._sender_trip_map.get(sender_id)
        if caption and not trip_id:
            words = caption.strip().split()
            for w in words:
                if len(w) >= 4 and w.isalnum():
                    found_trip = self.register_join_code(sender_id, w)
                    if found_trip:
                        trip_id = found_trip
                        break

        # 3. File validation
        is_valid, err_msg = self.validate_upload(image_bytes)
        if not is_valid:
            return {
                "status": "invalid_file",
                "error": err_msg,
                "processing_card_png": None,
                "final_card_png": None,
            }

        lang = self.get_sender_language(sender_id)

        # 4. Immediate Processing Card
        processing_img = self.card_generator.generate_processing_card(language=lang)
        processing_png_bytes = self.card_generator.to_png_bytes(processing_img)

        # 5. Extraction Service Execution
        evidence, interpretation = self.extraction_service.process_screenshot(
            image_path_or_bytes=image_bytes,
            sender_id=sender_id,
            channel=channel,
            trip_id=trip_id,
        )

        # Update language preference if screenshot language was detected as Kannada
        if interpretation.language_detected == "kn" and lang == "en":
            lang = "kn"
            self.set_sender_language(sender_id, "kn")

        # 6. Save to Store (Member B contract)
        self.store_client.add_evidence(evidence)
        self.store_client.add_interpretation(interpretation)

        # 7. Generate Outcome Reply Card
        st = interpretation.screenshot_type
        fields = interpretation.fields

        if st == ScreenshotType.TICKET_QR:
            card_img = self.card_generator.generate_ticket_received_card(
                language=lang,
                link_type="EXACT" if fields.ticket_id else "INFERRED",
                ticket_id=fields.ticket_id,
                origin_station=fields.origin_station,
                destination_station=fields.destination_station,
                fare=fields.fare or fields.amount,
            )
        elif st in [ScreenshotType.UPI_SUCCESS, ScreenshotType.UPI_FAILED_PENDING, ScreenshotType.BOT_ERROR]:
            case_id = f"CASE-{evidence.evidence_id[-6:].upper()}"
            card_img = self.card_generator.generate_payment_missing_card(
                case_id=case_id,
                amount=fields.amount,
                utr=fields.utr,
                language=lang,
            )
        elif st == ScreenshotType.SUSPECT_NOTICE:
            card_img = self.card_generator.generate_needs_evidence_card(
                requested_item="Official metro bot receipt",
                reason="Message looks suspicious or unverified by transit authority",
                language=lang,
            )
        elif st == ScreenshotType.OTHER or interpretation.type_confidence < 0.60:
            card_img = self.card_generator.generate_could_not_read_card(
                guidance="Image could not be reliably classified. Please ensure the amount and route are visible.",
                language=lang,
            )
        else:
            # Bank SMS or claim submission
            card_img = self.card_generator.generate_ticket_received_card(
                language=lang,
                link_type="INFERRED",
                fare=fields.amount,
            )

        final_png_bytes = self.card_generator.to_png_bytes(card_img)

        return {
            "status": "success",
            "processing_card_png": processing_png_bytes,
            "final_card_png": final_png_bytes,
            "evidence_id": evidence.evidence_id,
            "interp_id": interpretation.interp_id,
            "screenshot_type": st.value,
            "type_confidence": interpretation.type_confidence,
            "fields": fields.model_dump(),
        }

    def handle_adaptive_challenge(
        self,
        evidence_id: str,
        requested_item: str,
        reason: str,
        sender_id: str,
    ) -> bytes:
        """
        Fulfills Section 1.4: Member B calls POST /challenge/{id}
        Member A generates and returns the adaptive evidence challenge card PNG.
        """
        lang = self.get_sender_language(sender_id)
        card_img = self.card_generator.generate_needs_evidence_card(
            requested_item=requested_item,
            reason=reason,
            language=lang,
        )
        return self.card_generator.to_png_bytes(card_img)
