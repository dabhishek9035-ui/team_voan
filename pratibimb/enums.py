"""Shared contract enums (identical in all three Member files)."""

SCREENSHOT_TYPES = (
    "TICKET_QR", "UPI_SUCCESS", "UPI_FAILED_PENDING", "BANK_SMS", "REFUND_NOTICE",
    "BOT_ERROR", "CLAIM_SUBMISSION", "SUSPECT_NOTICE", "OTHER",
)

REL_TYPES = ("EXACT", "INFERRED", "MANUAL", "UNMATCHED")

# Decision.action. A MANUAL relationship is always paired with a 'manual_link' decision.
DECISION_ACTIONS = ("approved", "rejected", "proof_requested", "manual_link")

# Section 1.3 of the contract: the fields{} object Member A must produce.
FIELD_KEYS = (
    "amount", "currency", "timestamp", "utr", "order_id", "ticket_id", "qr_payload",
    "origin_station", "destination_station", "fare", "payer_name_masked", "payee_name",
    "status_text", "app_name", "bank_name", "language_detected",
)

FIELD_SOURCES = ("sarvam_extract", "sarvam_digitise", "qr_decoder", "llm_structuring")

EVIDENCE_STATUSES = ("received", "quarantined")

# id prefix -> table
ID_PREFIXES = {"ev_": "evidence", "in_": "interpretations", "rl_": "relationships", "dc_": "decisions"}
