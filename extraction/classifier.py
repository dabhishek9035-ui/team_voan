"""
Screenshot Classifier for Pratibimb Member A.
Two-tier classification:
  Tier 1: High-precision deterministic rules on extracted text and image properties.
  Tier 2: Sarvam-105B LLM structuring for ambiguous cases.
Handles SUSPECT_NOTICE (refund/KYC scams) and falls back honestly to OTHER.
"""

from __future__ import annotations
import re
from typing import Tuple, Dict, Any, Optional
from intake.models import ScreenshotType
from extraction.sarvam_client import SarvamClient


class ScreenshotClassifier:
    """
    Classifies screenshots into one of the 9 standard ScreenshotType enums.
    """

    CONFIDENCE_THRESHOLD = 0.60

    def __init__(self, sarvam_client: Optional[SarvamClient] = None):
        self.sarvam_client = sarvam_client or SarvamClient()

    def classify(
        self,
        raw_text: str,
        has_qr_code: bool = False,
        qr_payload: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classifies screenshot using two-step pipeline.
        Returns:
            {
                "screenshot_type": ScreenshotType,
                "confidence": float,
                "reason": str,
                "classifier_step": "rule" | "sarvam_105b" | "threshold_fallback"
            }
        """
        if not raw_text and not has_qr_code:
            return {
                "screenshot_type": ScreenshotType.OTHER,
                "confidence": 0.1,
                "reason": "No text and no QR code detected in image",
                "classifier_step": "threshold_fallback",
            }

        # Step 1: Fast deterministic rule-based evaluation
        rule_type, rule_conf, rule_reason = self._classify_rules(
            raw_text, has_qr_code, qr_payload
        )

        if rule_type is not None and rule_conf >= 0.80:
            return {
                "screenshot_type": rule_type,
                "confidence": rule_conf,
                "reason": rule_reason,
                "classifier_step": "rule",
            }

        # Step 2: Sarvam-105B LLM structuring for ambiguous cases
        llm_type, llm_conf, llm_reason = self.sarvam_client.classify_with_sarvam_105b(raw_text)

        # Re-check confidence threshold
        if llm_conf < self.CONFIDENCE_THRESHOLD:
            return {
                "screenshot_type": ScreenshotType.OTHER,
                "confidence": llm_conf,
                "reason": f"Low confidence ({llm_conf:.2f} < {self.CONFIDENCE_THRESHOLD}): {llm_reason}",
                "classifier_step": "threshold_fallback",
            }

        return {
            "screenshot_type": llm_type,
            "confidence": llm_conf,
            "reason": llm_reason,
            "classifier_step": "sarvam_105b",
        }

    def _classify_rules(
        self,
        text: str,
        has_qr_code: bool,
        qr_payload: Optional[str],
    ) -> Tuple[Optional[ScreenshotType], float, str]:
        """High-precision pattern matcher for common transit and payment screens."""
        t = text.lower() if text else ""

        # Check 1: SUSPECT_NOTICE (Scam alerts, phishing, fraudulent refund claims)
        # BMRCL explicitly warns against APK downloads, links or numbers claiming refund assistance.
        suspect_keywords = [
            r"metro.*refund.*click\s+here",
            r"download.*apk.*metro",
            r"install.*(?:anydesk|teamviewer|rustdesk).*refund",
            r"kyc.*(?:suspended|blocked).*call",
            r"claim.*failed.*refund.*(?:bit\.ly|tinyurl|wa\.me)",
            r"dear\s+customer.*metro\s+recharge\s+failed.*call\s+\d{10}",
        ]
        for pattern in suspect_keywords:
            if re.search(pattern, t):
                return (
                    ScreenshotType.SUSPECT_NOTICE,
                    0.96,
                    "Matches known transit refund phishing or scam pattern",
                )

        # Check 2: BOT_ERROR (Metro WhatsApp bot error / booking failure)
        bot_error_keywords = [
            "booking failed",
            "failed booking",
            "refunded to source within 7 working days",
            "could not generate your qr ticket",
            "oops! something went wrong",
            "money debited but ticket not booked",
            "we could not complete your booking",
        ]
        for kw in bot_error_keywords:
            if kw in t:
                return (
                    ScreenshotType.BOT_ERROR,
                    0.93,
                    f"Matches WhatsApp metro bot booking error string: '{kw}'",
                )

        # Check 3: REFUND_NOTICE (Official refund processing notice or bank refund credit)
        if "refund" in t:
            if any(w in t for w in ["refund of rs", "refund initiated", "refund processed", "credited back to your source", "refund successful"]):
                return (
                    ScreenshotType.REFUND_NOTICE,
                    0.92,
                    "Official refund confirmation or reversal notice",
                )

        # Check 4: TICKET_QR (Metro QR ticket screen)
        # Distinct presence of QR code + metro transit keywords
        metro_transit_cues = any(w in t for w in ["namma metro", "bmrcl", "bengaluru metro", "single journey", "entry station", "exit station", "valid till"])
        if has_qr_code and (metro_transit_cues or "ticket" in t or "fare" in t or (qr_payload and "BMRCL" in qr_payload)):
            return (
                ScreenshotType.TICKET_QR,
                0.98,
                "Decoded transit QR code with metro travel markers",
            )
        if not has_qr_code and metro_transit_cues and ("ticket id" in t or "qr ticket" in t):
            # Even if local QR wasn't decoded (e.g. low res), text clearly confirms it's a ticket screen
            return (
                ScreenshotType.TICKET_QR,
                0.86,
                "Metro ticket layout markers identified from text",
            )

        # Check 5: UPI_FAILED_PENDING (Payment failure, processing, or pending)
        upi_failed_cues = [
            "payment failed",
            "transaction failed",
            "payment processing",
            "payment pending",
            "money will be refunded if debited",
            "bank server did not respond",
            "payment could not be completed",
        ]
        for cue in upi_failed_cues:
            if cue in t:
                return (
                    ScreenshotType.UPI_FAILED_PENDING,
                    0.94,
                    f"Identified payment failure or pending state: '{cue}'",
                )

        # Check 6: UPI_SUCCESS (Payment success screen from GPay, PhonePe, Paytm, BHIM, etc.)
        upi_success_cues = [
            "paid successfully",
            "payment successful",
            "transaction successful",
            "upi ref no",
            "upi transaction id",
            "google transaction id",
            "paid to bmrcl",
            "paid to bangalore metro",
        ]
        if any(cue in t for cue in upi_success_cues):
            return (
                ScreenshotType.UPI_SUCCESS,
                0.95,
                "UPI payment success indicators confirmed",
            )

        # Check 7: BANK_SMS (SMS notification from bank)
        sms_cues = ["debited for rs", "debited by inr", "credited to a/c", "linked to upi", "bank alert", "avl bal"]
        if any(cue in t for cue in sms_cues):
            return (
                ScreenshotType.BANK_SMS,
                0.92,
                "Bank transaction SMS format recognized",
            )

        # Check 8: CLAIM_SUBMISSION (Reimbursement form or portal submission)
        if any(w in t for w in ["reimbursement claim", "expense report", "conveyance claim", "claim submission"]):
            return (
                ScreenshotType.CLAIM_SUBMISSION,
                0.89,
                "Reimbursement claim form indicators found",
            )

        # Ambiguous - let LLM handle
        return None, 0.0, "No clear rule match"
