"""The append-only store.

Public surface (Day 1): add_trip, add_traveller, add_evidence, add_interpretation,
add_relationship, add_decision, log_access, get, history, is_current, list_records,
interpretations_for, snapshot_hash, chain_head, verify.

There is deliberately NO update or delete method. Corrections are new records with
`supersedes` pointing at the old one. The current view is the latest non-superseded record.
"""
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone

from . import validate as v
from .canon import GENESIS, canonical_json, compute_hash
from .enums import ID_PREFIXES
from .errors import NotFoundError, SupersedeError, ValidationError
from .schema import (APPEND_ONLY_TABLES, RECORD_SPECS, SCHEMA_SQL, SCHEMA_VERSION,
                     SPEC_BY_PREFIX, trigger_sql)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return prefix + uuid.uuid4().hex[:12]


def row_to_record(spec, row) -> dict:
    """DB row -> dict with JSON columns parsed. Includes prev_hash and record_hash."""
    rec = {spec.pk: row[spec.pk]}
    for c in spec.columns:
        val = row[c]
        rec[c] = json.loads(val) if (c in spec.json_cols and val is not None) else val
    rec["prev_hash"] = row["prev_hash"]
    rec["record_hash"] = row["record_hash"]
    return rec


def record_body(spec, rec: dict) -> dict:
    """The exact object that gets hashed: everything except prev_hash and record_hash."""
    return {k: rec[k] for k in [spec.pk, *spec.columns]}


class Store:
    def __init__(self, path=":memory:", clock=None):
        self.path = str(path)
        self._clock = clock or utc_now
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        # Needed so a conflict-replace (which deletes the old row implicitly) also trips the delete triggers.
        self.conn.execute("PRAGMA recursive_triggers=ON")
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA_SQL)
        self.conn.executescript(trigger_sql())
        self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------ internals
    def _now(self):
        return self._clock()

    def _head_locked(self) -> str:
        row = self.conn.execute("SELECT record_hash FROM audit_chain ORDER BY seq DESC LIMIT 1").fetchone()
        return row["record_hash"] if row else GENESIS

    def _exists(self, table, pk, value) -> bool:
        return self.conn.execute(f"SELECT 1 FROM {table} WHERE {pk} = ?", (value,)).fetchone() is not None

    def _spec_for_id(self, record_id):
        if not isinstance(record_id, str):
            raise ValidationError("record id must be a string")
        for prefix, spec in SPEC_BY_PREFIX.items():
            if record_id.startswith(prefix):
                return spec
        raise ValidationError(f"unrecognised record id {record_id!r}")

    def _check_supersedes(self, spec, supersedes):
        """Run inside the write transaction so two writers cannot both supersede one record."""
        if supersedes is None:
            return None
        if not isinstance(supersedes, str) or not supersedes.startswith(spec.prefix):
            raise SupersedeError(f"supersedes must be a {spec.table} id ({spec.prefix}...)")
        if not self._exists(spec.table, spec.pk, supersedes):
            raise SupersedeError(f"cannot supersede unknown record {supersedes}")
        taken = self.conn.execute(
            f"SELECT {spec.pk} FROM {spec.table} WHERE supersedes = ?", (supersedes,)).fetchone()
        if taken:
            raise SupersedeError(f"{supersedes} is already superseded by {taken[0]}")
        return supersedes

    def _append(self, spec, rid, values: dict, pre_checks=()):
        """Atomically write one record plus its chain link."""
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                for check in pre_checks:
                    check()
                prev = self._head_locked()
                body = {spec.pk: rid, **{c: values[c] for c in spec.columns}}
                record_hash = compute_hash(body, prev)
                cols = [spec.pk, *spec.columns, "prev_hash", "record_hash"]
                params = [rid]
                for c in spec.columns:
                    val = values[c]
                    params.append(canonical_json(val) if (c in spec.json_cols and val is not None) else val)
                params += [prev, record_hash]
                self.conn.execute(
                    f"INSERT INTO {spec.table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", params)
                self.conn.execute(
                    "INSERT INTO audit_chain (record_type, record_id, prev_hash, record_hash, created_at) "
                    "VALUES (?,?,?,?,?)", (spec.table, rid, prev, record_hash, values["created_at"]))
                self.conn.execute("COMMIT")
            except sqlite3.IntegrityError as e:
                self.conn.execute("ROLLBACK")
                raise ValidationError(f"rejected by database constraint: {e}") from e
            except Exception:
                self.conn.execute("ROLLBACK")
                raise
        return rid

    def _need(self, table, pk, value, label):
        if not self._exists(table, pk, value):
            raise NotFoundError(f"{label} {value!r} does not exist")

    # ------------------------------------------------------------------ trips / travellers
    def add_trip(self, name, coordinator_id, trip_id=None, window_start=None, window_end=None) -> str:
        v.require_str("name", name)
        v.require_str("coordinator_id", coordinator_id)
        tid = trip_id or new_id("trip_")
        try:
            with self._lock:
                if window_start is not None:
                    v.timestamp("window_start", window_start)
                if window_end is not None:
                    v.timestamp("window_end", window_end)
                self.conn.execute("INSERT INTO trips VALUES (?,?,?,?,?,?)",
                                  (tid, name, coordinator_id, self._now(), window_start, window_end))
        except sqlite3.IntegrityError as e:
            raise ValidationError(f"trip rejected: {e}") from e
        return tid

    def add_traveller(self, trip_id, sender_id, label=None) -> str:
        v.require_str("sender_id", sender_id)
        self._need("trips", "trip_id", trip_id, "trip")
        tid = new_id("trv_")
        try:
            with self._lock:
                self.conn.execute("INSERT INTO travellers VALUES (?,?,?,?,?)",
                                  (tid, trip_id, sender_id, label, self._now()))
        except sqlite3.IntegrityError as e:
            raise ValidationError(f"traveller rejected: {e}") from e
        return tid

    # ------------------------------------------------------------------ the four records
    def add_evidence(self, sender_id, channel, received_at, sha256, phash=None, ahash=None,
                     file_ref=None, trip_id=None, status="received", supersedes=None,
                     evidence_id=None) -> str:
        spec = RECORD_SPECS["evidence"]
        values = {
            "trip_id": v.require_str("trip_id", trip_id, allow_none=True),
            "sender_id": v.require_str("sender_id", sender_id),
            "channel": v.require_str("channel", channel),
            "received_at": v.timestamp("received_at", received_at),
            "file_ref": v.require_str("file_ref", file_ref, allow_none=True),
            "sha256": v.hex_string("sha256", sha256, 64),
            "phash": v.hex_string("phash", phash, allow_none=True),
            "ahash": v.hex_string("ahash", ahash, allow_none=True),
            "status": v.evidence_status(status),
            "supersedes": supersedes,
            "created_at": self._now(),
        }
        rid = evidence_id or new_id(spec.prefix)
        if not rid.startswith(spec.prefix):
            raise ValidationError(f"evidence_id must start with {spec.prefix}")
        checks = [lambda: self._check_supersedes(spec, supersedes)]
        if trip_id is not None:
            checks.insert(0, lambda: self._need("trips", "trip_id", trip_id, "trip"))
        return self._append(spec, rid, values, checks)

    def add_interpretation(self, evidence_id, producer, model_version, screenshot_type,
                           type_confidence, fields, field_confidence, field_source=None,
                           sarvam_job_id=None, raw_text_ref=None, language_detected=None,
                           supersedes=None, interp_id=None) -> str:
        spec = RECORD_SPECS["interpretations"]
        f, c, s = v.interpretation_fields(fields, field_confidence, field_source)
        values = {
            "evidence_id": v.require_str("evidence_id", evidence_id),
            "producer": v.require_str("producer", producer),
            "model_version": v.require_str("model_version", model_version),
            "sarvam_job_id": v.require_str("sarvam_job_id", sarvam_job_id, allow_none=True),
            "screenshot_type": v.screenshot_type(screenshot_type),
            "type_confidence": v.unit_float("type_confidence", type_confidence),
            "fields": f, "field_confidence": c, "field_source": s,
            "raw_text_ref": v.require_str("raw_text_ref", raw_text_ref, allow_none=True),
            "language_detected": v.require_str("language_detected", language_detected, allow_none=True),
            "supersedes": supersedes,
            "created_at": self._now(),
        }
        rid = interp_id or new_id(spec.prefix)
        if not rid.startswith(spec.prefix):
            raise ValidationError(f"interp_id must start with {spec.prefix}")

        def same_evidence():
            if supersedes is not None:
                old = self.conn.execute("SELECT evidence_id FROM interpretations WHERE interp_id = ?",
                                        (supersedes,)).fetchone()
                if old and old["evidence_id"] != evidence_id:
                    raise SupersedeError("a re-extraction must refer to the same evidence as the one it supersedes")

        return self._append(spec, rid, values, [
            lambda: self._need("evidence", "evidence_id", evidence_id, "evidence"),
            lambda: self._check_supersedes(spec, supersedes),
            same_evidence])

    def add_relationship(self, from_id, to_id, type, basis, score, reason, created_by,
                         supersedes=None, rel_id=None) -> str:
        spec = RECORD_SPECS["relationships"]
        rtype = v.rel_type(type)
        v.require_str("reason", reason)
        v.require_str("created_by", created_by)
        basis = v.basis_list(basis)
        score = v.unit_float("score", score, allow_none=True)
        if rtype in ("EXACT", "INFERRED"):
            if to_id is None or not basis or score is None:
                raise ValidationError(f"{rtype} needs to_id, a non-empty basis and a score")
            if not created_by.startswith("system:"):
                raise ValidationError(f"{rtype} must be created_by 'system:...' (machine-observed)")
        elif rtype == "MANUAL":
            if to_id is None:
                raise ValidationError("MANUAL needs to_id")
            if not created_by.startswith("coordinator:"):
                raise ValidationError("MANUAL must be created_by 'coordinator:...' (a human link)")
        v.require_str("from_id", from_id)
        if to_id is not None:
            v.require_str("to_id", to_id)
            if to_id == from_id:
                raise ValidationError("a record cannot be related to itself")
        for label, rid_ in (("from_id", from_id), ("to_id", to_id)):
            if rid_ is not None and not (rid_.startswith("ev_") or rid_.startswith("in_")):
                raise ValidationError(f"{label} must be an evidence (ev_) or interpretation (in_) id")
        values = {"from_id": from_id, "to_id": to_id, "type": rtype, "basis": basis, "score": score,
                  "reason": reason, "created_by": created_by, "supersedes": supersedes,
                  "created_at": self._now()}
        rid = rel_id or new_id(spec.prefix)
        if not rid.startswith(spec.prefix):
            raise ValidationError(f"rel_id must start with {spec.prefix}")

        def endpoints():
            for rid_ in (from_id, to_id):
                if rid_ is not None:
                    s = self._spec_for_id(rid_)
                    self._need(s.table, s.pk, rid_, "record")

        return self._append(spec, rid, values, [endpoints, lambda: self._check_supersedes(spec, supersedes)])

    def add_decision(self, subject_ref, action, decided_by, reason, seen_snapshot_hash,
                     supersedes=None, dec_id=None) -> str:
        spec = RECORD_SPECS["decisions"]
        v.require_str("subject_ref", subject_ref)
        decided_by = v.require_str("decided_by", decided_by)
        if not decided_by.startswith("coordinator:"):
            raise ValidationError("decisions are human: decided_by must start with 'coordinator:'")
        values = {"subject_ref": subject_ref, "action": v.decision_action(action),
                  "decided_by": decided_by, "reason": v.require_str("reason", reason),
                  "seen_snapshot_hash": v.hex_string("seen_snapshot_hash", seen_snapshot_hash, 64),
                  "supersedes": supersedes, "created_at": self._now()}
        rid = dec_id or new_id(spec.prefix)
        if not rid.startswith(spec.prefix):
            raise ValidationError(f"dec_id must start with {spec.prefix}")

        def subject_exists():
            s = self._spec_for_id(subject_ref)
            self._need(s.table, s.pk, subject_ref, "subject")

        return self._append(spec, rid, values, [subject_exists, lambda: self._check_supersedes(spec, supersedes)])

    # ------------------------------------------------------------------ Day 2-7 side tables
    def _insert(self, sql, params, label):
        try:
            with self._lock:
                self.conn.execute(sql, params)
        except sqlite3.IntegrityError as e:
            raise ValidationError(f"{label} rejected: {e}") from e

    def add_join_code(self, trip_id, created_by, ttl_hours=72, code=None) -> dict:
        self._need("trips", "trip_id", trip_id, "trip")
        code = code or uuid.uuid4().hex[:8].upper()
        now = self._now()
        exp = (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(hours=ttl_hours)) \
            .isoformat(timespec="milliseconds").replace("+00:00", "Z")
        self._insert("INSERT INTO join_codes VALUES (?,?,?,?,?)", (code, trip_id, created_by, now, exp), "join code")
        return {"code": code, "trip_id": trip_id, "expires_at": exp}

    def get_join_code(self, code):
        r = self.conn.execute("SELECT * FROM join_codes WHERE code = ?", (code,)).fetchone()
        return dict(r) if r else None

    def add_assertion(self, trip_id, sender_id, subject_ref=None, kind="traveller_asserts_travel") -> str:
        v.require_str("sender_id", sender_id)
        self._need("trips", "trip_id", trip_id, "trip")
        aid = new_id("as_")
        self._insert("INSERT INTO assertions VALUES (?,?,?,?,?,?)",
                     (aid, trip_id, sender_id, kind, subject_ref, self._now()), "assertion")
        return aid

    def list_assertions(self, trip_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM assertions WHERE trip_id = ? ORDER BY rowid", (trip_id,))]

    def add_case_row(self, case_ref, trip_id, state, evidence_refs, opened_at, last_action=None, supersedes=None) -> str:
        self._need("trips", "trip_id", trip_id, "trip")
        rid = new_id("cr_")
        self._insert("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?)",
                     (rid, case_ref, trip_id, state, canonical_json(sorted(evidence_refs)), opened_at,
                      last_action, self._now(), supersedes), "case row")
        return rid

    def current_cases(self, trip_id=None):
        sql = ("SELECT * FROM cases WHERE case_row_id NOT IN (SELECT supersedes FROM cases WHERE supersedes IS NOT NULL)"
               + (" AND trip_id = ?" if trip_id else "") + " ORDER BY rowid")
        out = []
        for r in self.conn.execute(sql, (trip_id,) if trip_id else ()):
            d = dict(r)
            d["evidence_refs"] = json.loads(d["evidence_refs"])
            out.append(d)
        return out

    def add_challenge(self, subject_ref, trip_id, attribute, request_type, reason_code, message, due_at,
                      status="issued", response_evidence_id=None, supersedes=None) -> str:
        cid = new_id("ch_")
        self._insert("INSERT INTO challenges VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (cid, subject_ref, trip_id, attribute, request_type, reason_code, message, status, due_at,
                      response_evidence_id, self._now(), supersedes), "challenge")
        return cid

    def current_challenges(self, subject_ref=None, trip_id=None):
        sql = ("SELECT * FROM challenges WHERE challenge_id NOT IN "
               "(SELECT supersedes FROM challenges WHERE supersedes IS NOT NULL)")
        params = []
        if subject_ref:
            sql += " AND subject_ref = ?"; params.append(subject_ref)
        if trip_id:
            sql += " AND trip_id = ?"; params.append(trip_id)
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY rowid", params)]

    def get_trip(self, trip_id):
        r = self.conn.execute("SELECT * FROM trips WHERE trip_id = ?", (trip_id,)).fetchone()
        if r is None:
            raise NotFoundError(f"trip {trip_id!r} does not exist")
        return dict(r)

    def list_travellers(self, trip_id):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM travellers WHERE trip_id = ? ORDER BY rowid", (trip_id,))]

    # ------------------------------------------------------------------ access log
    def log_access(self, actor, action, subject_ref, reason) -> int:
        v.require_str("actor", actor)
        v.require_str("action", action)
        v.require_str("reason", reason)
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO access_log (actor, action, subject_ref, reason, at) VALUES (?,?,?,?,?)",
                (actor, action, subject_ref, reason, self._now()))
        return cur.lastrowid

    def access_log(self):
        return [dict(r) for r in self.conn.execute("SELECT * FROM access_log ORDER BY log_id")]

    # ------------------------------------------------------------------ reads
    def get(self, record_id) -> dict:
        spec = self._spec_for_id(record_id)
        row = self.conn.execute(f"SELECT * FROM {spec.table} WHERE {spec.pk} = ?", (record_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"{record_id} not found")
        return row_to_record(spec, row)

    def is_current(self, record_id) -> bool:
        spec = self._spec_for_id(record_id)
        self.get(record_id)
        return self.conn.execute(
            f"SELECT 1 FROM {spec.table} WHERE supersedes = ?", (record_id,)).fetchone() is None

    def history(self, record_id) -> list:
        """Whole correction chain containing record_id, oldest first."""
        spec = self._spec_for_id(record_id)
        rec = self.get(record_id)
        back = [rec]
        while back[0]["supersedes"]:
            back.insert(0, self.get(back[0]["supersedes"]))
        fwd = []
        cur = record_id
        while True:
            row = self.conn.execute(
                f"SELECT * FROM {spec.table} WHERE supersedes = ?", (cur,)).fetchone()
            if row is None:
                break
            fwd.append(row_to_record(spec, row))
            cur = row[spec.pk]
        return back + fwd

    def list_records(self, table, current_only=True, **filters) -> list:
        if table not in RECORD_SPECS:
            raise ValidationError(f"unknown record table {table!r}")
        spec = RECORD_SPECS[table]
        allowed = {spec.pk, *spec.columns}
        bad = set(filters) - allowed
        if bad:
            raise ValidationError(f"unknown filter columns: {sorted(bad)}")
        where, params = [], []
        for k, val in filters.items():
            where.append(f"{k} = ?")
            params.append(val)
        if current_only:
            where.append(f"{spec.pk} NOT IN (SELECT supersedes FROM {table} WHERE supersedes IS NOT NULL)")
        sql = f"SELECT * FROM {table}" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY rowid"
        return [row_to_record(spec, r) for r in self.conn.execute(sql, params)]

    def interpretations_for(self, evidence_id, current_only=True) -> list:
        return self.list_records("interpretations", current_only=current_only, evidence_id=evidence_id)

    def snapshot_hash(self, record_ids) -> str:
        """Fingerprint of exactly what a human was shown: sha256 over [id, record_hash] pairs."""
        import hashlib
        pairs = [[rid, self.get(rid)["record_hash"]] for rid in record_ids]
        return hashlib.sha256(canonical_json(pairs).encode("utf-8")).hexdigest()

    def chain_head(self) -> str:
        with self._lock:
            return self._head_locked()

    def chain_length(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM audit_chain").fetchone()[0]

    def counts(self) -> dict:
        return {t: self.conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in RECORD_SPECS}

    def verify(self, expected_head=None, expected_length=None) -> dict:
        from .audit import verify_chain
        return verify_chain(self.conn, expected_head=expected_head, expected_length=expected_length)
