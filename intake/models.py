"""
Core data models and contracts for Pratibimb Member A (Intake & Extraction).
Strictly adheres to Section 1 of docs/01_Member_A_Intake_and_Extraction.md.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ScreenshotType(str, Enum):
    """The 9 agreed screenshot types across Pratibimb."""
    TICKET_QR = "TICKET_QR"
    UPI_SUCCESS = "UPI_SUCCESS"
    UPI_FAILED_PENDING = "UPI_FAILED_PENDING"
    BANK_SMS = "BANK_SMS"
    REFUND_NOTICE = "REFUND_NOTICE"
    BOT_ERROR = "BOT_ERROR"
    CLAIM_SUBMISSION = "CLAIM_SUBMISSION"
    SUSPECT_NOTICE = "SUSPECT_NOTICE"
    OTHER = "OTHER"


class RelationshipType(str, Enum):
    """Relationship types survival contract."""
    EXACT = "EXACT"
    INFERRED = "INFERRED"
    MANUAL = "MANUAL"
    UNMATCHED = "UNMATCHED"


class EvidenceLevel(str, Enum):
    """Evidence levels scoped to specific claim attributes."""
    EXTRACTED = "EXTRACTED"
    CORROBORATED = "CORROBORATED"
    INDEPENDENTLY_VERIFIED = "INDEPENDENTLY_VERIFIED"


class ExtractedFields(BaseModel):
    """
    Standard extracted fields from screenshots.
    Nulls are valid. Invented values are bugs.
    """
    amount: Optional[float] = None
    currency: Optional[str] = "INR"
    timestamp: Optional[str] = None  # ISO format string or standardized representation
    utr: Optional[str] = None
    order_id: Optional[str] = None
    ticket_id: Optional[str] = None
    qr_payload: Optional[str] = None
    origin_station: Optional[str] = None
    destination_station: Optional[str] = None
    fare: Optional[float] = None
    payer_name_masked: Optional[str] = None
    payee_name: Optional[str] = None
    status_text: Optional[str] = None
    app_name: Optional[str] = None
    bank_name: Optional[str] = None
    language_detected: Optional[str] = None

    class Config:
        extra = "forbid"


class EvidenceRecord(BaseModel):
    """
    Evidence record representing what the user submitted.
    Immutable, append-only.
    """
    evidence_id: str
    trip_id: Optional[str] = None
    sender_id: str
    channel: str  # e.g., 'telegram', 'whatsapp_sandbox'
    received_at: str  # ISO timestamp
    file_ref: str
    sha256: str
    phash: str
    ahash: Optional[str] = None
    status: str = "received"  # received, processed, retained, deleted


class InterpretationRecord(BaseModel):
    """
    Interpretation record representing what the system extracted.
    Immutable, append-only. Re-extraction produces a new Interpretation.
    """
    interp_id: str
    evidence_id: str
    producer: str  # e.g. 'pratibimb-intake-v1'
    model_version: str  # e.g. 'sarvam-vision-1.5+105b'
    sarvam_job_id: Optional[str] = None
    screenshot_type: ScreenshotType
    type_confidence: float = Field(ge=0.0, le=1.0)
    fields: ExtractedFields
    field_confidence: Dict[str, float] = Field(default_factory=dict)
    field_sources: Dict[str, str] = Field(default_factory=dict)
    raw_text_ref: Optional[str] = None
    language_detected: Optional[str] = None
    created_at: str
    supersedes: Optional[str] = None
    qr_payload_parseable: Optional[bool] = None
    normalized_corrections: List[Dict[str, Any]] = Field(default_factory=list)
