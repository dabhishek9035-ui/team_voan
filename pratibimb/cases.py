"""B5. Case logic. Cases open automatically; they are resolved ONLY by evidence plus a human Decision."""
import hashlib

from . import claims as cl
from .errors import ValidationError


def case_ref(root):
    return "CASE-" + hashlib.sha256(root.encode()).hexdigest()[:8].upper()


def reconcile(store, trip_id, cfg, now=None):
    """Close the loop on payments that never found a ticket: record an UNMATCHED relationship once the
    wait exceeds N hours, then sync case rows. Idempotent."""
    now = now or cl.now_utc()
    made = []
    for c in cl.build_claims(store, trip_id, cfg, now):
        if c["state"] != "case_opened":
            continue
        for m in c["interp_ids"]:
            if c["types"][m] != "UPI_SUCCESS":
                continue
            if any(r["from_id"] == m or r["to_id"] == m for r in c["relationships"]):
                continue
            rid = store.add_relationship(
                m, None, "UNMATCHED", [], None,
                f"No ticket seen {cfg['no_ticket_hours']} or more hours after this payment.", "system:case-engine")
            made.append(rid)
    return made


def sync_cases(store, trip_id, cfg, now=None):
    """Write versioned case rows. A case exists for any claim in case_opened / refund_evidence_seen, or
    one that has human action. Returns current case views including the stale flag (derived, not stored)."""
    now = now or cl.now_utc()
    current = {c["case_ref"]: c for c in store.current_cases(trip_id)}
    out = []
    for c in cl.build_claims(store, trip_id, cfg, now):
        in_case = c["state"] in ("case_opened", "refund_evidence_seen")
        if not in_case and ref_exists(current, c) is None:
            continue
        ref = case_ref(c["root"])
        state = "resolved" if c["resolved"] else c["state"]
        refs = sorted({*c["interp_ids"], *c["context_ids"], *[r["rel_id"] for r in c["relationships"]]})
        prev = current.get(ref)
        if prev is None or prev["state"] != state or prev["evidence_refs"] != refs or prev["last_action"] != c["last_action"]:
            opened = prev["opened_at"] if prev else now.isoformat().replace("+00:00", "Z")
            store.add_case_row(ref, trip_id, state, refs, opened, c["last_action"],
                               supersedes=prev["case_row_id"] if prev else None)
        row = {x["case_ref"]: x for x in store.current_cases(trip_id)}[ref]
        opened_dt = cl.vw.parse_ts(row["opened_at"])
        # age = elapsed time since the payment (what refund windows are measured against), not since the row was written
        age_h = c["age_hours"] if c["age_hours"] is not None else round((now - opened_dt).total_seconds() / 3600, 2)
        out.append({"case_ref": ref, "claim_ref": c["claim_ref"], "state": row["state"],
                    "evidence_refs": row["evidence_refs"], "age_hours": age_h, "opened_at": row["opened_at"], "last_action": row["last_action"],
                    "stale": row["state"] != "resolved" and age_h >= cfg["stale_case_hours"]})
    return out


def ref_exists(current, c):
    return current.get(case_ref(c["root"]))
