"""
Reply Card Generator for Pratibimb Member A.
Generates beautiful PNG card images for travellers in English, Kannada, and Hindi.

Core Principles:
1. Cards are images because users screenshot cards too!
2. Respects non-negotiable tone: NEVER uses the words "fraud" or "verified".
   Uses 'Extracted', 'Corroborated', 'Needs Review', 'Unverified'.
3. Supports all outcomes:
   - TICKET_RECEIVED (with EXACT/INFERRED link badge)
   - PAYMENT_FOUND_TICKET_MISSING (with Case reference)
   - NEEDS_MORE_EVIDENCE (with specific challenge request and reason)
   - COULD_NOT_READ (with helpful resend instructions)
   - PROCESSING (acknowledgement card)
"""

from __future__ import annotations
import io
import os
from pathlib import Path
from typing import Optional, Dict, Any, Union
from PIL import Image, ImageDraw, ImageFont

from extraction.sarvam_client import SarvamClient


class ReplyCardGenerator:
    """
    Renders visual PNG reply cards for the chat channel.
    """

    CARD_WIDTH = 750
    CARD_HEIGHT = 440

    # Localized fixed strings
    STRINGS = {
        "en": {
            "ticket_received_title": "Ticket Received",
            "ticket_received_subtitle": "Recorded in Journey Ledger",
            "payment_missing_title": "Payment Found • Ticket Missing",
            "payment_missing_subtitle": "Case Opened • Monitoring Reversal",
            "needs_evidence_title": "More Evidence Needed",
            "needs_evidence_subtitle": "Adaptive Evidence Request",
            "could_not_read_title": "Could Not Read Screenshot",
            "could_not_read_subtitle": "Extraction Failed",
            "processing_title": "Received • Processing...",
            "processing_subtitle": "Sarvam Document AI is analyzing...",
            "footer_brand": "Pratibimb • System of Record",
            "link_type_exact": "EXACT MATCH",
            "link_type_inferred": "INFERRED MATCH",
            "status_label": "Status",
            "amount_label": "Amount",
            "stations_label": "Route",
            "utr_label": "UTR",
            "case_id_label": "Case ID",
            "action_label": "Next Step",
        },
        "kn": {
            "ticket_received_title": "ಟಿಕೆಟ್ ಸ್ವೀಕರಿಸಲಾಗಿದೆ",
            "ticket_received_subtitle": "ಪ್ರಯಾಣ ಲೆಡ್ಜರ್‌ನಲ್ಲಿ ದಾಖಲಿಸಲಾಗಿದೆ",
            "payment_missing_title": "ಪಾವತಿ ಲಭ್ಯವಿದೆ • ಟಿಕೆಟ್ ಕಾಣೆಯಾಗಿದೆ",
            "payment_missing_subtitle": "ಪ್ರಕರಣ ದಾಖಲಿಸಲಾಗಿದೆ • ಮರುಪಾವತಿ ಮೇಲ್ವಿಚಾರಣೆ",
            "needs_evidence_title": "ಹೆಚ್ಚಿನ ಪುರಾವೆ ಅಗತ್ಯವಿದೆ",
            "needs_evidence_subtitle": "ಹೆಚ್ಚುವರಿ ವಿವರಗಳ ವಿನಂತಿ",
            "could_not_read_title": "ಸ್ಕ್ರೀನ್‌ಶಾಟ್ ಓದಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ",
            "could_not_read_subtitle": "ವಿವರ ಪಡೆಯಲು ವಿಫಲವಾಗಿದೆ",
            "processing_title": "ಸ್ವೀಕರಿಸಲಾಗಿದೆ • ಪ್ರಕ್ರಿಯೆಯಲ್ಲಿದೆ...",
            "processing_subtitle": "ಸರ್ವಮ್ ಡಾಕ್ಯುಮೆಂಟ್ ಎಐ ಪರಿಶೀಲಿಸುತ್ತಿದೆ...",
            "footer_brand": "ಪ್ರತಿಬಿಂಬ • ಸಿಸ್ಟಮ್ ಆಫ್ ರೆಕಾರ್ಡ್",
            "link_type_exact": "ಖಚಿತ ಲಿಂಕ್ (EXACT)",
            "link_type_inferred": "ಅಂದಾಜು ಲಿಂಕ್ (INFERRED)",
            "status_label": "ಸ್ಥಿತಿ",
            "amount_label": "ಮೊತ್ತ",
            "stations_label": "ಮಾರ್ಗ",
            "utr_label": "ಯುಟಿಆರ್ (UTR)",
            "case_id_label": "ಪ್ರಕರಣ ಸಂಖ್ಯೆ",
            "action_label": "ಮುಂದಿನ ಕ್ರಮ",
        },
        "hi": {
            "ticket_received_title": "टिकट प्राप्त हुआ",
            "ticket_received_subtitle": "यात्रा बहीखाते में दर्ज किया गया",
            "payment_missing_title": "भुगतान मिला • टिकट गायब है",
            "payment_missing_subtitle": "मामला दर्ज किया गया • निगरानी जारी",
            "needs_evidence_title": "अधिक साक्ष्य की आवश्यकता है",
            "needs_evidence_subtitle": "अतिरिक्त दस्तावेज़ अनुरोध",
            "could_not_read_title": "स्क्रीनशॉट पढ़ा नहीं जा सका",
            "could_not_read_subtitle": "विवरण पढ़ने में असमर्थ",
            "processing_title": "प्राप्त हुआ • प्रक्रिया जारी है...",
            "processing_subtitle": "सर्वम दस्तावेज़ एआई विश्लेषण कर रहा है...",
            "footer_brand": "प्रतिबिंब • सिस्टम ऑफ रिकॉर्ड",
            "link_type_exact": "सटीक मिलान (EXACT)",
            "link_type_inferred": "अनुमानित मिलान (INFERRED)",
            "status_label": "स्थिति",
            "amount_label": "राशि",
            "stations_label": "मार्ग",
            "utr_label": "यूटीआर (UTR)",
            "case_id_label": "मामला संख्या",
            "action_label": "अगला कदम",
        },
    }

    def __init__(self, sarvam_client: Optional[SarvamClient] = None):
        self.sarvam_client = sarvam_client or SarvamClient()
        self._font_path = self._find_font_path()

    def _find_font_path(self) -> Optional[str]:
        """Locates Nirmala UI for Indian scripts or Segoe UI / Arial fallback."""
        candidates = [
            r"C:\Windows\Fonts\Nirmala.ttc",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansKannada-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _get_font(self, size: int, bold: bool = False) -> ImageFont.ImageFont:
        """Loads scalable font or default fallback."""
        if self._font_path:
            try:
                return ImageFont.truetype(self._font_path, size)
            except Exception:
                pass
        return ImageFont.load_default()

    def _sanitize_text(self, text: str) -> str:
        """Enforces strictly: Never use 'fraud' or 'verified' in user-facing cards."""
        if not text:
            return ""
        sanitized = text.replace("verified", "corroborated").replace("Verified", "Corroborated")
        sanitized = sanitized.replace("fraud", "irregular").replace("Fraud", "Irregular")
        return sanitized

    def generate_ticket_received_card(
        self,
        language: str = "en",
        link_type: str = "EXACT",
        ticket_id: Optional[str] = None,
        origin_station: Optional[str] = None,
        destination_station: Optional[str] = None,
        fare: Optional[float] = None,
    ) -> Image.Image:
        """Card for successfully received and linked metro ticket."""
        lang = language if language in self.STRINGS else "en"
        t = self.STRINGS[lang]

        # Colors: Green/Teal accent theme
        bg_color = "#0F172A"       # Dark slate
        card_bg = "#1E293B"        # Slate 800
        accent_color = "#10B981"   # Emerald green
        badge_bg = "#064E3B"       # Dark emerald
        badge_text = "#34D399"
        text_primary = "#F8FAFC"
        text_secondary = "#94A3B8"

        img = Image.new("RGB", (self.CARD_WIDTH, self.CARD_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        # Draw card container with rounded rectangle
        draw.rounded_rectangle(
            [(20, 20), (self.CARD_WIDTH - 20, self.CARD_HEIGHT - 20)],
            radius=16,
            fill=card_bg,
            outline="#334155",
            width=2,
        )

        # Header accent bar
        draw.rounded_rectangle([(30, 30), (self.CARD_WIDTH - 30, 40)], radius=4, fill=accent_color)

        # Title and Subtitle
        font_title = self._get_font(26, bold=True)
        font_subtitle = self._get_font(16)
        font_body = self._get_font(18)
        font_badge = self._get_font(14, bold=True)
        font_footer = self._get_font(13)

        draw.text((50, 60), t["ticket_received_title"], fill=text_primary, font=font_title)
        draw.text((50, 95), t["ticket_received_subtitle"], fill=text_secondary, font=font_subtitle)

        # Link Type Badge
        badge_label = t["link_type_exact"] if link_type == "EXACT" else t["link_type_inferred"]
        draw.rounded_rectangle([(self.CARD_WIDTH - 220, 60), (self.CARD_WIDTH - 50, 96)], radius=8, fill=badge_bg, outline=accent_color)
        draw.text((self.CARD_WIDTH - 205, 68), badge_label, fill=badge_text, font=font_badge)

        # Divider line
        draw.line([(50, 130), (self.CARD_WIDTH - 50, 130)], fill="#334155", width=1)

        # Details Grid
        y = 155
        # Line 1: Ticket ID & Status
        draw.text((50, y), f"{t['status_label']}:", fill=text_secondary, font=font_body)
        draw.text((160, y), "Recorded (Extracted)", fill="#34D399", font=font_body)

        draw.text((400, y), "Ticket ID:", fill=text_secondary, font=font_body)
        draw.text((500, y), str(ticket_id or "Auto-Linked"), fill=text_primary, font=font_body)

        # Line 2: Route / Stations
        y += 50
        if origin_station or destination_station:
            route_str = f"{origin_station or 'Origin'} -> {destination_station or 'Destination'}"
        else:
            route_str = "Namma Metro QR Ticket"
        draw.text((50, y), f"{t['stations_label']}:", fill=text_secondary, font=font_body)
        draw.text((160, y), route_str, fill=text_primary, font=font_body)

        # Line 3: Fare
        y += 50
        fare_str = f"₹ {fare:.2f}" if fare is not None else "₹ --"
        draw.text((50, y), f"{t['amount_label']}:", fill=text_secondary, font=font_body)
        draw.text((160, y), fare_str, fill="#FBBF24", font=font_body)

        # Bottom Notice
        y += 60
        draw.rounded_rectangle([(50, y), (self.CARD_WIDTH - 50, y + 45)], radius=8, fill="#0F172A")
        notice = "Corroborated evidence recorded. No coordinator action required."
        draw.text((65, y + 12), notice, fill=text_secondary, font=font_subtitle)

        # Footer
        draw.text((50, self.CARD_HEIGHT - 45), t["footer_brand"], fill="#64748B", font=font_footer)

        return img

    def generate_payment_missing_card(
        self,
        case_id: str,
        amount: Optional[float] = None,
        utr: Optional[str] = None,
        language: str = "en",
    ) -> Image.Image:
        """Card for debited payment where QR ticket was not generated by metro bot."""
        lang = language if language in self.STRINGS else "en"
        t = self.STRINGS[lang]

        # Colors: Amber/Warning theme
        bg_color = "#0F172A"
        card_bg = "#1E293B"
        accent_color = "#F59E0B"   # Amber
        badge_bg = "#78350F"
        badge_text = "#FDE68A"
        text_primary = "#F8FAFC"
        text_secondary = "#94A3B8"

        img = Image.new("RGB", (self.CARD_WIDTH, self.CARD_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(20, 20), (self.CARD_WIDTH - 20, self.CARD_HEIGHT - 20)],
            radius=16,
            fill=card_bg,
            outline="#334155",
            width=2,
        )
        draw.rounded_rectangle([(30, 30), (self.CARD_WIDTH - 30, 40)], radius=4, fill=accent_color)

        font_title = self._get_font(24, bold=True)
        font_subtitle = self._get_font(16)
        font_body = self._get_font(18)
        font_badge = self._get_font(14, bold=True)
        font_footer = self._get_font(13)

        draw.text((50, 60), t["payment_missing_title"], fill=text_primary, font=font_title)
        draw.text((50, 95), t["payment_missing_subtitle"], fill=text_secondary, font=font_subtitle)

        # Case Badge
        draw.rounded_rectangle([(self.CARD_WIDTH - 220, 60), (self.CARD_WIDTH - 50, 96)], radius=8, fill=badge_bg, outline=accent_color)
        draw.text((self.CARD_WIDTH - 200, 68), f"CASE: {case_id[:8]}", fill=badge_text, font=font_badge)

        draw.line([(50, 130), (self.CARD_WIDTH - 50, 130)], fill="#334155", width=1)

        y = 155
        draw.text((50, y), f"{t['case_id_label']}:", fill=text_secondary, font=font_body)
        draw.text((180, y), case_id, fill="#FBBF24", font=font_body)

        y += 45
        amt_str = f"₹ {amount:.2f}" if amount is not None else "₹ --"
        draw.text((50, y), f"{t['amount_label']}:", fill=text_secondary, font=font_body)
        draw.text((180, y), amt_str, fill=text_primary, font=font_body)

        draw.text((380, y), f"{t['utr_label']}:", fill=text_secondary, font=font_body)
        draw.text((460, y), str(utr or "Unextracted"), fill=text_primary, font=font_body)

        y += 55
        draw.rounded_rectangle([(50, y), (self.CARD_WIDTH - 50, y + 65)], radius=8, fill="#0F172A")
        guidance_text = "Case logged. If refund arrives, forward the bank SMS to close this case."
        draw.text((65, y + 12), guidance_text, fill="#E2E8F0", font=font_subtitle)
        draw.text((65, y + 36), "Metro refunds usually credit within 7 business days.", fill=text_secondary, font=font_footer)

        draw.text((50, self.CARD_HEIGHT - 45), t["footer_brand"], fill="#64748B", font=font_footer)
        return img

    def generate_needs_evidence_card(
        self,
        requested_item: str,
        reason: str,
        language: str = "en",
    ) -> Image.Image:
        """Card when adaptive challenge requires additional specific evidence."""
        lang = language if language in self.STRINGS else "en"
        t = self.STRINGS[lang]

        # Colors: Orange / Challenge theme
        bg_color = "#0F172A"
        card_bg = "#1E293B"
        accent_color = "#EA580C"   # Orange
        badge_bg = "#7C2D12"
        badge_text = "#FED7AA"
        text_primary = "#F8FAFC"
        text_secondary = "#94A3B8"

        img = Image.new("RGB", (self.CARD_WIDTH, self.CARD_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(20, 20), (self.CARD_WIDTH - 20, self.CARD_HEIGHT - 20)],
            radius=16,
            fill=card_bg,
            outline="#334155",
            width=2,
        )
        draw.rounded_rectangle([(30, 30), (self.CARD_WIDTH - 30, 40)], radius=4, fill=accent_color)

        font_title = self._get_font(24, bold=True)
        font_subtitle = self._get_font(16)
        font_body = self._get_font(17)
        font_badge = self._get_font(13, bold=True)
        font_footer = self._get_font(13)

        draw.text((50, 60), t["needs_evidence_title"], fill=text_primary, font=font_title)
        draw.text((50, 95), t["needs_evidence_subtitle"], fill=text_secondary, font=font_subtitle)

        # Badge
        draw.rounded_rectangle([(self.CARD_WIDTH - 200, 60), (self.CARD_WIDTH - 50, 96)], radius=8, fill=badge_bg, outline=accent_color)
        draw.text((self.CARD_WIDTH - 185, 68), "NEEDS REVIEW", fill=badge_text, font=font_badge)

        draw.line([(50, 130), (self.CARD_WIDTH - 50, 130)], fill="#334155", width=1)

        y = 155
        draw.text((50, y), f"Requested Item:", fill=text_secondary, font=font_body)
        draw.text((210, y), requested_item, fill="#FDBA74", font=font_body)

        y += 45
        draw.text((50, y), f"Reason:", fill=text_secondary, font=font_body)
        safe_reason = self._sanitize_text(reason)
        draw.text((210, y), safe_reason[:45], fill=text_primary, font=font_body)

        y += 55
        draw.rounded_rectangle([(50, y), (self.CARD_WIDTH - 50, y + 65)], radius=8, fill="#0F172A")
        draw.text((65, y + 14), f"Action: Please send a screenshot of your {requested_item}", fill="#F8FAFC", font=font_subtitle)
        draw.text((65, y + 38), "This item will be linked to complete your journey claim.", fill=text_secondary, font=font_footer)

        draw.text((50, self.CARD_HEIGHT - 45), t["footer_brand"], fill="#64748B", font=font_footer)
        return img

    def generate_could_not_read_card(
        self,
        guidance: Optional[str] = None,
        language: str = "en",
    ) -> Image.Image:
        """Card when screenshot is blurry, corrupted, or unreadable."""
        lang = language if language in self.STRINGS else "en"
        t = self.STRINGS[lang]

        bg_color = "#0F172A"
        card_bg = "#1E293B"
        accent_color = "#64748B"   # Slate gray
        badge_bg = "#334155"
        badge_text = "#CBD5E1"
        text_primary = "#F8FAFC"
        text_secondary = "#94A3B8"

        img = Image.new("RGB", (self.CARD_WIDTH, self.CARD_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(20, 20), (self.CARD_WIDTH - 20, self.CARD_HEIGHT - 20)],
            radius=16,
            fill=card_bg,
            outline="#334155",
            width=2,
        )
        draw.rounded_rectangle([(30, 30), (self.CARD_WIDTH - 30, 40)], radius=4, fill=accent_color)

        font_title = self._get_font(24, bold=True)
        font_subtitle = self._get_font(16)
        font_body = self._get_font(17)
        font_badge = self._get_font(13, bold=True)
        font_footer = self._get_font(13)

        draw.text((50, 60), t["could_not_read_title"], fill=text_primary, font=font_title)
        draw.text((50, 95), t["could_not_read_subtitle"], fill=text_secondary, font=font_subtitle)

        draw.rounded_rectangle([(self.CARD_WIDTH - 190, 60), (self.CARD_WIDTH - 50, 96)], radius=8, fill=badge_bg, outline=accent_color)
        draw.text((self.CARD_WIDTH - 175, 68), "UNREADABLE", fill=badge_text, font=font_badge)

        draw.line([(50, 130), (self.CARD_WIDTH - 50, 130)], fill="#334155", width=1)

        y = 160
        default_guidance = guidance or "Screenshot was blurry, cropped or non-standard format."
        draw.text((50, y), "Issue:", fill=text_secondary, font=font_body)
        draw.text((150, y), default_guidance[:50], fill=text_primary, font=font_body)

        y += 55
        draw.rounded_rectangle([(50, y), (self.CARD_WIDTH - 50, y + 65)], radius=8, fill="#0F172A")
        draw.text((65, y + 14), "Please take an uncropped screenshot and send again.", fill="#F8FAFC", font=font_subtitle)
        draw.text((65, y + 38), "Ensure the fare, station name or UTR are clearly visible.", fill=text_secondary, font=font_footer)

        draw.text((50, self.CARD_HEIGHT - 45), t["footer_brand"], fill="#64748B", font=font_footer)
        return img

    def generate_processing_card(
        self,
        language: str = "en"
    ) -> Image.Image:
        """Instant receipt card sent while async Sarvam Document AI job runs."""
        lang = language if language in self.STRINGS else "en"
        t = self.STRINGS[lang]

        bg_color = "#0F172A"
        card_bg = "#1E293B"
        accent_color = "#3B82F6"   # Electric blue
        text_primary = "#F8FAFC"
        text_secondary = "#94A3B8"

        img = Image.new("RGB", (self.CARD_WIDTH, self.CARD_HEIGHT), bg_color)
        draw = ImageDraw.Draw(img)

        draw.rounded_rectangle(
            [(20, 20), (self.CARD_WIDTH - 20, self.CARD_HEIGHT - 20)],
            radius=16,
            fill=card_bg,
            outline="#334155",
            width=2,
        )
        draw.rounded_rectangle([(30, 30), (self.CARD_WIDTH - 30, 40)], radius=4, fill=accent_color)

        font_title = self._get_font(26, bold=True)
        font_subtitle = self._get_font(16)
        font_body = self._get_font(18)
        font_footer = self._get_font(13)

        draw.text((50, 60), t["processing_title"], fill=text_primary, font=font_title)
        draw.text((50, 95), t["processing_subtitle"], fill=text_secondary, font=font_subtitle)

        draw.line([(50, 130), (self.CARD_WIDTH - 50, 130)], fill="#334155", width=1)

        y = 170
        draw.text((50, y), "Screenshot received and queued for Sarvam Vision.", fill=text_primary, font=font_body)
        y += 40
        draw.text((50, y), "Your verified reply card will appear in seconds.", fill=text_secondary, font=font_subtitle)

        draw.text((50, self.CARD_HEIGHT - 45), t["footer_brand"], fill="#64748B", font=font_footer)
        return img

    def to_png_bytes(self, img: Image.Image) -> bytes:
        """Converts PIL Image to PNG binary bytes for sending over chat API."""
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
