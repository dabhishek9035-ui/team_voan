"""Duplicate signals. Similarity is deliberately never treated as proof."""
from datetime import datetime

from .config import DEFAULT_CONFIG

IDENTIFIERS = ("ticket_id", "utr", "order_id", "qr_payload")


def _distance(left, right):
    if not left or not right:
        return None
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except (TypeError, ValueError):
        return None


def duplicate_signals(store, evidence_id, config=DEFAULT_CONFIG):
    evidence = store.get(evidence_id)
    interpretations = store.list_records("interpretations", current_only=True)
    current = [i for i in interpretations if i["evidence_id"] != evidence_id]
    result = []
    for other in store.list_records("evidence", current_only=True):
        if other["evidence_id"] == evidence_id:
            continue
        if other["sha256"] == evidence["sha256"]:
            result.append({"layer": "exact_file", "evidence_id": other["evidence_id"],
                           "same_sender": other["sender_id"] == evidence["sender_id"],
                           "signal": "same file fingerprint"})
        distance = _distance(evidence.get("phash"), other.get("phash"))
        if distance is not None and distance <= config.phash_hamming_threshold:
            result.append({"layer": "perceptual", "evidence_id": other["evidence_id"],
                           "distance": distance, "signal": "looks similar; not a conclusion"})
    for interp in current:
        if interp["evidence_id"] == evidence_id:
            continue
        for key in IDENTIFIERS:
            value = interp["fields"].get(key)
            if value is None:
                continue
            for candidate in interpretations:
                if candidate["interp_id"] == interp["interp_id"]:
                    continue
                if candidate["fields"].get(key) == value:
                    result.append({"layer": "semantic", "attribute": key,
                                   "interpretation_id": candidate["interp_id"],
                                   "signal": "normalised identifier seen earlier"})
                    break
    return result
