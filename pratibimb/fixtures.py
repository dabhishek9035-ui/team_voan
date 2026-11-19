"""Load fixtures/scenarios.json into a Store. Used by tests, the demo and (from Day 2) the API seed."""
import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "scenarios.json")


def load_fixture_file(path=None):
    with open(path or DEFAULT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def load_into(store, path=None, only=None) -> dict:
    """`only` = optional list of scenario names (duplicate scenarios share hashes on purpose, so
    load them one per store when testing duplicate detection). Returns {scenario_name: {"keys": {key: {"evidence_id", "interp_id"}}, "relationships": [...],
    "decisions": [...], "expect": {...}}}. Every scenario gets its own travellers' evidence under one trip."""
    data = load_fixture_file(path)
    t = data["trip"]
    store.add_trip(t["name"], t["coordinator_id"], trip_id=t["trip_id"],
                   window_start=t.get("window_start"), window_end=t.get("window_end"))
    for tr in data["travellers"]:
        store.add_traveller(t["trip_id"], tr["sender_id"], tr.get("label"))
    index = {}
    for sc in data["scenarios"]:
        if only is not None and sc["name"] not in only:
            continue
        keys, rels, decs = {}, [], []
        for it in sc["items"]:
            ev = store.add_evidence(it["sender_id"], it["channel"], it["received_at"], it["sha256"],
                                    phash=it["phash"], ahash=it.get("ahash"), trip_id=t["trip_id"],
                                    file_ref=f"fixture://{sc['name']}/{it['key']}")
            i = it["interpretation"]
            ip = store.add_interpretation(
                ev, i["producer"], i["model_version"], i["screenshot_type"], i["type_confidence"],
                i["fields"], i["field_confidence"], i["field_source"], sarvam_job_id=i.get("sarvam_job_id"),
                language_detected=i.get("language_detected"))
            keys[it["key"]] = {"evidence_id": ev, "interp_id": ip}
        for r in sc["relationships"]:
            basis = [({k: keys[val]["interp_id"] for k, val in b.items()} if isinstance(b, dict) else b)
                     for b in r["basis"]]
            rid = store.add_relationship(
                keys[r["from"]]["interp_id"], keys[r["to"]]["interp_id"] if r["to"] else None,
                r["type"], basis, r["score"], r["reason"], r["created_by"])
            rels.append(rid)
        for d in sc["decisions"]:
            subj = keys[d["subject"]]["interp_id"]
            did = store.add_decision(subj, d["action"], d["decided_by"], d["reason"], store.snapshot_hash([subj]))
            decs.append(did)
        index[sc["name"]] = {"keys": keys, "relationships": rels, "decisions": decs, "expect": sc["expect"]}
    return index
