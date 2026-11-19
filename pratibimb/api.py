"""Unified WSGI HTTP API for Pratibimb (Members A, B, and C)."""
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import cases, challenge, claims, linking, privacy, trust, views as vw
from .config import load_config
from .enums import FIELD_SOURCES
from .errors import NotFoundError, PratibimbError

_REL_ORDER = {"EXACT": 0, "MANUAL": 1, "INFERRED": 2, "UNMATCHED": 3}


def _reply(start_response, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(status, [("Content-Type", "application/json"),
                            ("Content-Length", str(len(body)))])
    return [body]


def _ensure_trip_and_traveller(store, trip_id, sender_id):
    if not trip_id:
        return
    try:
        store.get_trip(trip_id)
    except Exception:
        store.add_trip(trip_id, "coordinator:auto", trip_id=trip_id)
    if sender_id and not any(t["sender_id"] == sender_id for t in store.list_travellers(trip_id)):
        store.add_traveller(trip_id, sender_id, label=sender_id)


def _sanitize_interp_payload(payload):
    iid = payload.get("interp_id")
    if isinstance(iid, str) and iid.startswith("int_"):
        iid = "in_" + iid[4:]
    fields = dict(payload.get("fields") or {})
    raw_conf = dict(payload.get("field_confidence") or {})
    raw_src = dict(payload.get("field_source") or payload.get("field_sources") or {})
    clean_conf, clean_src = {}, {}
    for k, val in fields.items():
        if val is None:
            clean_conf[k] = 0.0
            clean_src[k] = None
        else:
            c = raw_conf.get(k, 0.9)
            clean_conf[k] = float(c) if c and float(c) > 0.0 else 0.9
            s = raw_src.get(k)
            clean_src[k] = s if s in FIELD_SOURCES else "sarvam_digitise"
    return iid, fields, clean_conf, clean_src


def _resolve_root_ev_id(store, claim):
    root_interp = store.get(claim["root"])
    return root_interp["evidence_id"]


def _assessed_claims(store, trip_id, cfg):
    trip = store.get_trip(trip_id) if trip_id else None
    built = claims.build_claims(store, trip_id, cfg)
    for c in built:
        c.update(trust.assess(store, c, cfg, trip))
    return trip, built


def _sender_name_map(store, trip_id):
    if not trip_id:
        return {}
    return {t["sender_id"]: (t["label"] or t["sender_id"]) for t in store.list_travellers(trip_id)}


def _build_inbox_items(store, trip_id, built, cfg):
    names = _sender_name_map(store, trip_id)
    case_by_ref = {cs["case_ref"]: cs for cs in cases.sync_cases(store, trip_id, cfg)} if trip_id else {}
    items = []
    for c in built:
        if c["decision_support"] == "clear" or c["resolved"]:
            continue
        its = c["_its"]
        root_it = its[c["root"]]
        ev = root_it["ev"]
        interp = root_it["interp"]
        f = privacy.mask_fields(interp["fields"])
        earlier = None
        for fl in c["dup_flags"]:
            if not fl["same_sender"]:
                earlier = {
                    "evidence_id": fl["earlier"],
                    "sender": names.get(fl["earlier_sender"], fl["earlier_sender"]),
                    "date": str(fl["earlier_received_at"])[:10],
                }
                break
        matched_case = next((cs for cs in case_by_ref.values() if cs["claim_ref"] == c["claim_ref"]), None)
        route = (f"{f['origin_station']} -> {f['destination_station']}"
                 if f.get("origin_station") and f.get("destination_station") else None)
        items.append({
            "evidence_id": ev["evidence_id"],
            "interp_id": c["root"],
            "claim_ref": c["claim_ref"],
            "screenshot_type": interp["screenshot_type"],
            "sender": names.get(c["sender_id"], c["sender_id"]),
            "amount": f.get("amount") if f.get("amount") is not None else f.get("fare"),
            "route": route,
            "status": "proof requested" if c["coordinator_decision"] == "proof_requested" else "open",
            "decision_support": c["decision_support"],
            "reasons": [s["plain_reason"] for s in c["signals"] if s["direction"] in ("concern", "info")] or [c["label"]],
            "relationship_type": c["relationship_type"],
            "evidence_level": c["evidence_level"],
            "earlier_sighting": earlier,
            "case_ref": matched_case["case_ref"] if matched_case else None,
        })
    return items


def _build_roster(store, trip_id, built, inbox_items):
    names = _sender_name_map(store, trip_id)
    all_items = vw.items(store, trip_id)
    in_inbox = {i["evidence_id"] for i in inbox_items}
    senders = list(names.keys())
    for it in all_items:
        sid = it["ev"]["sender_id"]
        if sid not in names:
            names[sid] = sid
            senders.append(sid)
    roster = []
    for sid in senders:
        mine = [it for it in all_items if it["ev"]["sender_id"] == sid]
        my_claims = [c for c in built if c["sender_id"] == sid]
        pays = any(it["interp"]["screenshot_type"] in vw.PAYMENT_TYPES for it in mine)
        ticks = any(it["interp"]["screenshot_type"] == "TICKET_QR" for it in mine)
        link = next((c["link_type"] for c in my_claims if c["link_type"]), None)
        if not link:
            link = next((c["relationship_type"] for c in my_claims if c["relationship_type"]), None)
        stuck = any(c["state"] in ("case_opened", "refund_evidence_seen") and not ticks for c in my_claims)
        flagged = any(it["ev"]["evidence_id"] in in_inbox for it in mine) or any(
            c["decision_support"] != "clear" and not c["resolved"] for c in my_claims)
        state = ("stuck" if stuck else
                 "needs review" if flagged else
                 "ready" if link in ("EXACT", "MANUAL") else
                 "pending" if (ticks or pays) else "no evidence yet")
        decs = [d for c in my_claims for d in c["decisions"]]
        decs.sort(key=lambda d: d["created_at"])
        roster.append({
            "traveller": names[sid],
            "sender_id": sid,
            "payment_seen": pays,
            "ticket_seen": ticks,
            "link_type": link,
            "state_machine_observed": state,
            "traveller_asserts_travel": any(c["traveller_asserts_travel"] for c in my_claims) or None,
            "coordinator_decision": decs[-1]["action"] if decs else None,
        })
    counts = {k: sum(r["state_machine_observed"] == k for r in roster)
              for k in ("ready", "needs review", "pending", "stuck", "no evidence yet")}
    return roster, counts


def _build_export_rows(store, trip_id, built):
    names = _sender_name_map(store, trip_id)
    rows = []
    for c in built:
        its = c["_its"]
        root_it = its[c["root"]]
        ev = root_it["ev"]
        f = privacy.mask_fields(root_it["interp"]["fields"])
        pay = next((privacy.mask_fields(its[m]["interp"]["fields"]) for m in c["interp_ids"]
                    if c["types"][m] in ("UPI_SUCCESS", "BANK_SMS")), None)
        tick = next((privacy.mask_fields(its[m]["interp"]["fields"]) for m in c["interp_ids"]
                     if c["types"][m] == "TICKET_QR"), None)
        rf = tick or f
        route = (f"{rf['origin_station']} -> {rf['destination_station']}"
                 if rf.get("origin_station") and rf.get("destination_station") else "")
        lv = c["evidence_level"]
        lv_str = "; ".join(f"{k}: {v}" for k, v in lv.items()) if lv else "none"
        last_dec = c["decisions"][-1] if c["decisions"] else None
        rows.append({
            "traveller": names.get(c["sender_id"], c["sender_id"]),
            "date": str(rf.get("timestamp") or ev["received_at"])[:10],
            "route": route,
            "fare": rf.get("fare") if rf.get("fare") is not None else rf.get("amount"),
            "ticket_reference": (tick or {}).get("ticket_id") or f.get("ticket_id") or "",
            "payment_reference": (pay or {}).get("utr") or "",
            "relationship_type": c["relationship_type"],
            "evidence_level": lv_str,
            "flags_with_reasons": " | ".join(s["plain_reason"] for s in c["signals"] if s["direction"] != "support"),
            "decision_support": c["decision_support"],
            "coordinator_decision": last_dec["action"] if last_dec else "",
            "decision_time": last_dec["created_at"] if last_dec else "",
            "evidence_id": ev["evidence_id"],
        })
    return sorted(rows, key=lambda r: (_REL_ORDER.get(r["relationship_type"], 9), r["date"]))


def create_app(store, config=None):
    cfg = config or load_config()

    def app(environ, start_response):
        parsed = urlparse(environ.get("RAW_URI", environ.get("PATH_INFO", "")))
        parts = [part for part in parsed.path.split("/") if part]
        query = parse_qs(parsed.query)
        method = environ.get("REQUEST_METHOD", "GET")
        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ.get("wsgi.input")
        payload = json.loads(raw.read(length) or b"{}") if length and raw else {}
        try:
            if method == "GET" and parts in ([], ["health"]):
                return _reply(start_response, "200 OK", {
                    "service": "Pratibimb Core Engine API",
                    "status": "ok",
                    "version": "0.3.0",
                    "endpoints": [
                        "/trips",
                        "/trips/{id}/summary",
                        "/trips/{id}/inbox",
                        "/records/{id}/trail",
                        "/decisions",
                        "/audit/verify",
                        "/export/claims",
                        "/openapi.json",
                    ],
                })
            if method == "GET" and parts == ["openapi.json"]:
                spec_path = Path(__file__).resolve().parents[1] / "openapi.json"
                if spec_path.exists():
                    return _reply(start_response, "200 OK", json.loads(spec_path.read_text(encoding="utf-8")))
            if method == "GET" and parts == ["trips"]:
                rows = store.conn.execute("SELECT * FROM trips ORDER BY rowid").fetchall()
                trips = [{
                    "trip_id": r["trip_id"], "name": r["name"], "coordinator_id": r["coordinator_id"],
                    "window_start": r["window_start"], "window_end": r["window_end"],
                } for r in rows]
                return _reply(start_response, "200 OK", trips)
            if method == "GET" and parts == ["trips", "lookup"]:
                code = (query.get("join_code") or [""])[0].strip().upper()
                row = store.get_join_code(code) if code else None
                if row is None:
                    return _reply(start_response, "404 Not Found", {"error": "join_code_not_found"})
                return _reply(start_response, "200 OK", row)
            if method == "POST" and parts == ["trips"]:
                trip_id = store.add_trip(payload["name"], payload["coordinator_id"],
                                         trip_id=payload.get("trip_id"),
                                         window_start=payload.get("window_start"),
                                         window_end=payload.get("window_end"))
                return _reply(start_response, "201 Created", {"trip_id": trip_id})
            if method == "POST" and len(parts) == 3 and parts[0] == "trips" and parts[2] == "join-code":
                result = store.add_join_code(parts[1], payload.get("created_by", "coordinator:api"),
                                             ttl_hours=payload.get("ttl_hours", cfg["join_code_ttl_hours"]),
                                             code=payload.get("code"))
                return _reply(start_response, "201 Created", result)
            if method == "POST" and parts == ["records", "evidence"]:
                trip_id = payload.get("trip_id")
                if trip_id is None:
                    row = store.conn.execute("SELECT trip_id FROM trips ORDER BY rowid LIMIT 1").fetchone()
                    if row:
                        trip_id = row["trip_id"]
                _ensure_trip_and_traveller(store, trip_id, payload["sender_id"])
                status = payload.get("status", "received")
                if status not in ("received", "quarantined"):
                    status = "received"
                eid = store.add_evidence(
                    sender_id=payload["sender_id"],
                    channel=payload["channel"],
                    received_at=payload["received_at"],
                    sha256=payload["sha256"],
                    phash=payload.get("phash"),
                    ahash=payload.get("ahash"),
                    file_ref=payload.get("file_ref"),
                    trip_id=trip_id,
                    status=status,
                    supersedes=payload.get("supersedes"),
                    evidence_id=payload.get("evidence_id"),
                )
                return _reply(start_response, "200 OK", {"evidence_id": eid})
            if method == "POST" and parts == ["records", "interpretation"]:
                iid, fields, clean_conf, clean_src = _sanitize_interp_payload(payload)
                stype = payload["screenshot_type"]
                if isinstance(stype, dict):
                    stype = stype.get("value", "OTHER")
                iid = store.add_interpretation(
                    evidence_id=payload["evidence_id"],
                    producer=payload["producer"],
                    model_version=payload["model_version"],
                    screenshot_type=stype,
                    type_confidence=float(payload["type_confidence"]),
                    fields=fields,
                    field_confidence=clean_conf,
                    field_source=clean_src,
                    sarvam_job_id=payload.get("sarvam_job_id"),
                    raw_text_ref=payload.get("raw_text_ref"),
                    language_detected=payload.get("language_detected"),
                    supersedes=payload.get("supersedes"),
                    interp_id=iid,
                )
                linking.link_interpretation(store, iid, cfg)
                ev = store.get(payload["evidence_id"])
                if ev.get("trip_id"):
                    cases.reconcile(store, ev["trip_id"], cfg)
                    cases.sync_cases(store, ev["trip_id"], cfg)
                    challenge.auto_respond(store, ev["trip_id"], cfg)
                return _reply(start_response, "200 OK", {"interp_id": iid})
            if method == "POST" and parts == ["decisions"]:
                subject_ref = payload["subject_ref"]
                action = payload["action"]
                decided_by = payload["decided_by"]
                if not decided_by.startswith("coordinator:"):
                    decided_by = f"coordinator:{decided_by}"
                reason = payload["reason"]
                snap = payload.get("seen_snapshot_hash") or store.snapshot_hash([subject_ref])
                link_to = payload.get("link_to")
                if action in ("link_manually", "manual_link") and link_to:
                    from_id = subject_ref
                    if from_id.startswith("ev_"):
                        its_from = store.interpretations_for(from_id)
                        if its_from:
                            from_id = its_from[-1]["interp_id"]
                    to_id = link_to
                    if to_id.startswith("ev_"):
                        its_to = store.interpretations_for(to_id)
                        if its_to:
                            to_id = its_to[-1]["interp_id"]
                    _, dec_id = linking.link_manual(store, from_id, to_id, decided_by, reason, snap)
                    return _reply(start_response, "201 Created", {"dec_id": dec_id})
                mapped_action = "manual_link" if action == "link_manually" else action
                dec_id = store.add_decision(
                    subject_ref=subject_ref,
                    action=mapped_action,
                    decided_by=decided_by,
                    reason=reason,
                    seen_snapshot_hash=snap,
                    supersedes=payload.get("supersedes"),
                    dec_id=payload.get("dec_id"),
                )
                return _reply(start_response, "201 Created", {"dec_id": dec_id})
            if method == "POST" and len(parts) == 2 and parts[0] == "challenge":
                result = challenge.issue(store, payload["trip_id"], parts[1], cfg)
                return _reply(start_response, "201 Created", result)
            if method == "POST" and len(parts) == 2 and parts[0] == "challenge-response":
                challenge.respond(store, parts[1], payload["evidence_id"])
                return _reply(start_response, "200 OK", {"challenge_id": parts[1], "status": "responded"})
            if method == "POST" and len(parts) == 2 and parts[0] == "raw-image":
                path = privacy.request_raw_image(store, parts[1], payload["actor"],
                                                 payload["reason"], cfg)
                return _reply(start_response, "200 OK", {"evidence_id": parts[1], "path": path})
            if method == "GET" and parts == ["audit", "verify"]:
                res = store.verify()
                broken = res.get("broken_at")
                res["broken_index"] = (broken["seq"] - 1) if broken and broken.get("seq") else None
                res["kind"] = broken.get("record_type") if broken else None
                return _reply(start_response, "200 OK", res)
            if method == "GET" and len(parts) == 3 and parts[0] == "trips" and parts[2] in ("summary", "inbox"):
                trip, built = _assessed_claims(store, parts[1], cfg)
                inbox_items = _build_inbox_items(store, parts[1], built, cfg)
                public_claims = [claims.public(c) for c in built]
                if parts[2] == "inbox":
                    inbox_claims = [c for c in public_claims if c["decision_support"] != "clear" and not c["resolved"]]
                    total_shots = len(vw.items(store, parts[1]))
                    return _reply(start_response, "200 OK", {
                        "trip_id": parts[1],
                        "travellers": store.list_travellers(parts[1]),
                        "claims": inbox_claims,
                        "needs_review": len(inbox_items),
                        "total_screenshots": total_shots,
                        "items": inbox_items,
                    })
                roster, counts = _build_roster(store, parts[1], built, inbox_items)
                return _reply(start_response, "200 OK", {
                    "trip_id": parts[1],
                    "trip": trip,
                    "travellers": store.list_travellers(parts[1]),
                    "claims": public_claims,
                    "counts": counts,
                    "roster": roster,
                })
            if method == "GET" and len(parts) == 3 and parts[0] == "records" and parts[2] == "trail":
                rid = parts[1]
                record = store.get(rid)
                ev_id = (record["evidence_id"] if rid.startswith("in_")
                         else rid if rid.startswith("ev_") else None)
                ev = privacy.view_evidence(store.get(ev_id)) if ev_id else None
                interps = ([privacy.view_interpretation(i)
                            for i in store.interpretations_for(ev_id, current_only=False)]
                           if ev_id else [])
                ref_ids = {rid} | ({ev_id} if ev_id else set()) | {i["interp_id"] for i in interps}
                rels = [r for r in store.list_records("relationships", current_only=False)
                        if r["from_id"] in ref_ids or r["to_id"] in ref_ids]
                rel_ids = {r["rel_id"] for r in rels}
                decs = [d for d in store.list_records("decisions", current_only=False)
                        if d["subject_ref"] in (ref_ids | rel_ids)]
                later = []
                for x in interps + rels + decs:
                    if x.get("supersedes"):
                        xid = x.get("interp_id") or x.get("rel_id") or x.get("dec_id")
                        later.append(f"{xid} supersedes {x['supersedes']}")
                return _reply(start_response, "200 OK", {
                    "record": record,
                    "evidence": ev,
                    "interpretations": interps,
                    "relationships": rels,
                    "decisions": decs,
                    "later_changes": later,
                })
            if method == "GET" and parts == ["export", "claims"]:
                trip_id = query.get("trip_id", [None])[0]
                _, built = _assessed_claims(store, trip_id, cfg)
                public_claims = [claims.public(c) for c in built]
                rows = _build_export_rows(store, trip_id, built)
                return _reply(start_response, "200 OK", {"claims": public_claims, "rows": rows})
            return _reply(start_response, "404 Not Found", {"error": "not_found"})
        except NotFoundError as exc:
            return _reply(start_response, "404 Not Found", {"error": str(exc)})
        except (PratibimbError, KeyError, ValueError, TypeError) as exc:
            return _reply(start_response, "400 Bad Request", {"error": str(exc)})
    return app
