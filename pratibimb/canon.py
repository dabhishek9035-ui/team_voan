"""Canonical JSON and the hash-chain primitive.

record_hash = SHA-256( canonical_json(record_body) + prev_hash )

One GLOBAL chain covers all four record types, in write order. Tamper EVIDENCE only:
anyone with write access to the database file can rewrite the whole chain, which is why
verify() accepts an externally stored head hash as an anchor. This is not a blockchain.
"""
import hashlib
import json

GENESIS = "0" * 64


def canonical_json(obj) -> str:
    """Deterministic JSON: sorted keys, no whitespace, UTF-8 preserved, no NaN/Infinity."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def compute_hash(body: dict, prev_hash: str) -> str:
    return hashlib.sha256((canonical_json(body) + prev_hash).encode("utf-8")).hexdigest()
