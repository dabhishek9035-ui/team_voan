"""B8. Privacy, masking and retention.

* The coordinator API returns FIELDS, never images. Fields are masked unless a Decision requires the full value.
* Raw-image access needs an explicit request (who, why) and is written to access_log.
* Retention: raw image is deleted when the claim is closed by a human decision OR after `raw_image_retention_days`.
  Deletion is an access_log entry (action `raw_image_deleted`), so it is logged and the record tables stay append-only.
* Honest wording: "masked fields plus fingerprints". Not zero-knowledge.
* NOT done here: encryption at rest of the image file. That belongs to Member A's lifecycle worker or disk-level
  encryption. This module only enforces access, logging and deletion.
"""
import os
import re
from datetime import timedelta

from . import claims as cl, views as vw
from .errors import NotFoundError, ValidationError

PHONE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
MASKED_KEYS = ("payer_name_masked", "payee_name", "utr", "order_id", "ticket_id", "qr_payload", "status_text")


def mask_name(v):
    parts = []
    for w in str(v).split():
        parts.append(w[0] + "*" * (len(w) - 1) if len(w) <= 2 else w[0] + "*" * (len(w) - 2) + w[-1])
    return " ".join(parts)


def mask_id(v):
    s = str(v)
    return "*" * max(len(s) - 4, 0) + s[-4:] if len(s) > 4 else "*" * len(s)


def mask_payload(v):
    s = str(v)
    return s[:4] + "…(hidden)" if len(s) > 4 else "(hidden)"


def hide_phones(v):
    return PHONE.sub("[phone hidden]", str(v))


def mask_fields(fields):
    out = dict(fields)
    for k, val in fields.items():
        if val is None:
            continue
        if k in ("payer_name_masked", "payee_name"):
            out[k] = hide_phones(mask_name(val))
        elif k in ("utr", "order_id", "ticket_id"):
            out[k] = mask_id(val)
        elif k == "qr_payload":
            out[k] = mask_payload(val)
        elif k == "status_text":
            out[k] = hide_phones(val)
    return out


def view_interpretation(interp):
    """Coordinator-safe copy: masked fields, no file reference, no raw-text reference."""
    d = dict(interp)
    d["fields"] = mask_fields(interp["fields"])
    d["raw_text_ref"] = None
    d["masked"] = True
    return d


def view_evidence(ev):
    d = dict(ev)
    d["file_ref"] = None            # fields, not images
    d["has_raw_image"] = ev["file_ref"] is not None
    return d


def reveal_fields(store, interp_id, actor, reason):
    """Full values, only for a coordinator, only where a Decision already exists on this subject. Logged."""
    if not (actor or "").startswith("coordinator:"):
        raise ValidationError("only a coordinator can reveal full values")
    if not (reason or "").strip():
        raise ValidationError("a reason is required")
    ip = store.get(interp_id)
    subjects = {interp_id, ip["evidence_id"]}
    if not any(d["subject_ref"] in subjects or interp_id in cl.interp_ids_for_subject(store, d["subject_ref"])
               for d in store.list_records("decisions")):
        raise ValidationError("full values need a Decision on this item first")
    store.log_access(actor, "reveal_full_fields", interp_id, reason)
    return dict(ip["fields"])


# ---------------------------------------------------------------- raw image
def _blob_path(cfg, file_ref):
    base = os.path.abspath(cfg["blob_dir"])
    path = os.path.abspath(os.path.join(base, file_ref))
    if os.path.commonpath([base, path]) != base:
        raise ValidationError("file_ref escapes the blob directory")
    return path


def image_deleted(store, evidence_id):
    return any(e["action"] == "raw_image_deleted" and e["subject_ref"] == evidence_id for e in store.access_log())


def request_raw_image(store, evidence_id, actor, reason, cfg):
    """Explicit, logged request. Returns the file path (the caller streams it). The attempt is logged even if denied."""
    if not (actor or "").startswith("coordinator:"):
        raise ValidationError("raw images are only available to a coordinator")
    if not (reason or "").strip():
        raise ValidationError("a reason is required")
    ev = store.get(evidence_id)
    store.log_access(actor, "raw_image_request", evidence_id, reason)
    if image_deleted(store, evidence_id):
        raise NotFoundError("the raw image has been deleted under the retention rule; fields and fingerprints remain")
    if not ev["file_ref"]:
        raise NotFoundError("no raw image is stored for this evidence")
    path = _blob_path(cfg, ev["file_ref"])
    if not os.path.exists(path):
        raise NotFoundError("raw image file is missing")
    store.log_access(actor, "raw_image_served", evidence_id, reason)
    return path


def retention_sweep(store, cfg, now=None, dry_run=False):
    """Delete raw images that are past retention or belong to a closed claim. Idempotent. Returns what was (or would be) deleted."""
    now = now or cl.now_utc()
    closed = set()
    for t in store.conn.execute("SELECT trip_id FROM trips"):
        for c in cl.build_claims(store, t["trip_id"], cfg, now):
            if c["resolved"]:
                closed.update(store.get(m)["evidence_id"] for m in c["interp_ids"])
    out = []
    for ev in store.list_records("evidence"):
        if not ev["file_ref"] or image_deleted(store, ev["evidence_id"]):
            continue
        age = now - vw.parse_ts(ev["received_at"])
        why = ("claim closed by a coordinator decision" if ev["evidence_id"] in closed
               else "retention period elapsed" if age > timedelta(days=cfg["raw_image_retention_days"]) else None)
        if not why:
            continue
        out.append({"evidence_id": ev["evidence_id"], "why": why})
        if dry_run:
            continue
        path = _blob_path(cfg, ev["file_ref"])
        if os.path.exists(path):
            os.remove(path)
        store.log_access("system:retention", "raw_image_deleted", ev["evidence_id"], why)
    return out
