"""Hash-chain verification. Recomputes everything from the database rows and reports the FIRST break.

Break reasons (in the order they are checked for each link):
  chain_gap                    a seq number is missing (a chain row was deleted)
  chain_prev_mismatch          chain row does not point at the previous link's hash
  record_missing               chain points at a record that no longer exists
  record_prev_mismatch         the record row's own prev_hash disagrees with the chain
  record_modified              recomputed hash of the record body != stored record_hash
  chain_hash_mismatch          chain row's hash != the record's stored hash
  record_not_in_chain          a record row exists that was never chained (inserted around the store)
  head_mismatch / length_mismatch  the external anchor disagrees (tail truncated or whole chain rewritten)

Honest limit: whoever can rewrite the whole database can recompute every hash. Store
`head_hash` somewhere else (print it, email it) and pass it as expected_head to catch that.
"""
from .canon import GENESIS, compute_hash
from .schema import RECORD_SPECS
from .store import record_body, row_to_record


def verify_chain(conn, expected_head=None, expected_length=None) -> dict:
    prev = GENESIS
    expected_seq = 1
    checked = 0
    first_break = None

    def brk(seq, rid, reason, detail):
        return {"seq": seq, "record_id": rid, "reason": reason, "detail": detail}

    for link in conn.execute("SELECT * FROM audit_chain ORDER BY seq"):
        seq, rid, rtype = link["seq"], link["record_id"], link["record_type"]
        if seq != expected_seq:
            first_break = brk(expected_seq, None, "chain_gap", f"expected seq {expected_seq}, found {seq}")
            break
        if link["prev_hash"] != prev:
            first_break = brk(seq, rid, "chain_prev_mismatch", "chain link does not follow the previous hash")
            break
        spec = RECORD_SPECS.get(rtype)
        row = None if spec is None else conn.execute(
            f"SELECT * FROM {spec.table} WHERE {spec.pk} = ?", (rid,)).fetchone()
        if row is None:
            first_break = brk(seq, rid, "record_missing", f"{rtype} {rid} is referenced by the chain but absent")
            break
        rec = row_to_record(spec, row)
        if rec["prev_hash"] != link["prev_hash"]:
            first_break = brk(seq, rid, "record_prev_mismatch", "record's prev_hash differs from the chain")
            break
        if compute_hash(record_body(spec, rec), rec["prev_hash"]) != rec["record_hash"]:
            first_break = brk(seq, rid, "record_modified", "record content no longer matches its hash")
            break
        if link["record_hash"] != rec["record_hash"]:
            first_break = brk(seq, rid, "chain_hash_mismatch", "chain hash differs from the record's hash")
            break
        prev = link["record_hash"]
        expected_seq += 1
        checked += 1

    orphans = []
    for spec in RECORD_SPECS.values():
        for r in conn.execute(
                f"SELECT {spec.pk} AS id FROM {spec.table} WHERE {spec.pk} NOT IN "
                f"(SELECT record_id FROM audit_chain WHERE record_type = ?)", (spec.table,)):
            orphans.append({"record_type": spec.table, "record_id": r["id"]})
    if first_break is None and orphans:
        o = orphans[0]
        first_break = brk(None, o["record_id"], "record_not_in_chain",
                          f"{o['record_type']} row exists with no audit_chain entry")

    if first_break is None and expected_length is not None and checked != expected_length:
        first_break = brk(checked, None, "length_mismatch",
                          f"chain has {checked} links, anchor says {expected_length}")
    if first_break is None and expected_head is not None and prev != expected_head:
        first_break = brk(checked, None, "head_mismatch", "chain head differs from the external anchor")

    return {"ok": first_break is None, "checked": checked, "head_hash": prev,
            "first_break": first_break, "orphans": orphans}
