"""Tunable settings. Windows, thresholds and the Day-0 gate switch live here, not in code.

Override with a JSON file: set PRATIBIMB_CONFIG=/path/to/config.json (only the keys you want to change).
All numeric values are PROPOSED defaults, not measured. B10 calibrates `clear_min_conf` on a labelled set.
"""
import json
import os

DEFAULTS = {
    # Day-0 gate result. "exact+inferred": real shared identifiers exist.
    # "inferred_only": no shared identifiers -> every link is INFERRED and goes to a human.
    "link_mode": "exact+inferred",
    "inferred_window_minutes": 15,       # payment <-> ticket time tolerance
    "refund_window_days": 45,            # refund must follow its payment within this
    "inferred_min_score": 0.6,
    "no_ticket_hours": 2,                # payment with no ticket after N hours -> case
    "stale_case_hours": 24 * 7,          # flag, not a rule: real refund windows vary (~7 working days or more)
    "trip_window_slack_hours": 0,
    "phash_hamming_threshold": 6,        # perceptual signal only
    "ahash_hamming_threshold": 6,
    "low_confidence": 0.6,               # key field below this = low_extraction_confidence
    "clear_min_conf": 0.85,              # min key-field confidence to auto-clear (calibrated in B10)
    "challenge_response_hours": 48,
    "join_code_ttl_hours": 72,
    "raw_image_retention_days": 30,
    "blob_dir": "blobs",
}


def load_config(overrides=None) -> dict:
    cfg = dict(DEFAULTS)
    path = os.environ.get("PRATIBIMB_CONFIG")
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            cfg.update(json.load(fh))
    if overrides:
        cfg.update(overrides)
    if cfg["link_mode"] not in ("exact+inferred", "inferred_only"):
        raise ValueError("link_mode must be 'exact+inferred' or 'inferred_only'")
    return cfg
