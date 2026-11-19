"""Read helpers shared by the engines: evidence joined with its current interpretation."""
import re
from datetime import datetime, timezone

PAYMENT_TYPES = ("UPI_SUCCESS", "BANK_SMS")
KEY_FIELDS = {  # fields whose unreadability or low confidence matters, per screenshot type
    "UPI_SUCCESS": ("amount", "utr", "timestamp"),
    "BANK_SMS": ("amount", "utr", "timestamp"),
    "TICKET_QR": ("ticket_id", "qr_payload", "timestamp"),
    "REFUND_NOTICE": ("amount", "timestamp"),
    "CLAIM_SUBMISSION": ("ticket_id", "timestamp"),
}


def parse_ts(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def norm_id(value):
    """Normalise an identifier for comparison: upper-case alphanumerics only."""
    if value is None:
        return None
    s = re.sub(r"[^0-9A-Za-z]", "", str(value)).upper()
    return s or None


def norm_payload(value):
    return None if value is None else re.sub(r"\s+", "", str(value)).upper() or None


def hamming(a, b):
    if not a or not b or len(a) != len(b):
        return None
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def items(store, trip_id=None):
    """Every current interpretation with its evidence, in ingest order: [{'interp':..,'ev':..}]."""
    out = []
    for ip in store.list_records("interpretations"):
        ev = store.get(ip["evidence_id"])
        if trip_id is not None and ev["trip_id"] != trip_id:
            continue
        out.append({"interp": ip, "ev": ev, "id": ip["interp_id"]})
    return out


def ids_of(it):
    f = it["interp"]["fields"]
    return {"utr": norm_id(f.get("utr")), "order_id": norm_id(f.get("order_id")),
            "ticket_id": norm_id(f.get("ticket_id")), "qr_payload": norm_payload(f.get("qr_payload"))}
