"""Database schema (v0.1) and the record specifications that drive hashing.

Append-only is enforced twice: (1) the Store exposes no update/delete method,
(2) SQLite triggers abort any UPDATE or DELETE on every table below.
"""
from dataclasses import dataclass

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class RecordSpec:
    table: str
    pk: str
    prefix: str
    columns: tuple        # ordered, excludes pk, prev_hash, record_hash
    json_cols: tuple = ()


EVIDENCE = RecordSpec(
    "evidence", "evidence_id", "ev_",
    ("trip_id", "sender_id", "channel", "received_at", "file_ref", "sha256", "phash", "ahash",
     "status", "supersedes", "created_at"))

INTERPRETATIONS = RecordSpec(
    "interpretations", "interp_id", "in_",
    ("evidence_id", "producer", "model_version", "sarvam_job_id", "screenshot_type",
     "type_confidence", "fields", "field_confidence", "field_source", "raw_text_ref",
     "language_detected", "supersedes", "created_at"),
    ("fields", "field_confidence", "field_source"))

RELATIONSHIPS = RecordSpec(
    "relationships", "rel_id", "rl_",
    ("from_id", "to_id", "type", "basis", "score", "reason", "created_by", "supersedes", "created_at"),
    ("basis",))

DECISIONS = RecordSpec(
    "decisions", "dec_id", "dc_",
    ("subject_ref", "action", "decided_by", "reason", "seen_snapshot_hash", "supersedes", "created_at"))

RECORD_SPECS = {s.table: s for s in (EVIDENCE, INTERPRETATIONS, RELATIONSHIPS, DECISIONS)}
SPEC_BY_PREFIX = {s.prefix: s for s in RECORD_SPECS.values()}

# Every table that must never be updated or deleted.
APPEND_ONLY_TABLES = ("evidence", "interpretations", "relationships", "decisions",
                      "audit_chain", "access_log", "trips", "travellers", "cases", "meta",
                      "join_codes", "assertions", "challenges")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
  trip_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  coordinator_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  window_start TEXT,
  window_end TEXT
);

CREATE TABLE IF NOT EXISTS travellers (
  traveller_id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(trip_id),
  sender_id TEXT NOT NULL,
  label TEXT,
  joined_at TEXT NOT NULL,
  UNIQUE (trip_id, sender_id)
);

CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  trip_id TEXT REFERENCES trips(trip_id),
  sender_id TEXT NOT NULL,
  channel TEXT NOT NULL,
  received_at TEXT NOT NULL,
  file_ref TEXT,
  sha256 TEXT NOT NULL CHECK (length(sha256) = 64),
  phash TEXT,
  ahash TEXT,
  status TEXT NOT NULL CHECK (status IN ('received','quarantined')),
  supersedes TEXT REFERENCES evidence(evidence_id),
  created_at TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_evidence_sha256 ON evidence(sha256);
CREATE INDEX IF NOT EXISTS idx_evidence_trip ON evidence(trip_id);

CREATE TABLE IF NOT EXISTS interpretations (
  interp_id TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  producer TEXT NOT NULL,
  model_version TEXT NOT NULL,
  sarvam_job_id TEXT,
  screenshot_type TEXT NOT NULL CHECK (screenshot_type IN
    ('TICKET_QR','UPI_SUCCESS','UPI_FAILED_PENDING','BANK_SMS','REFUND_NOTICE',
     'BOT_ERROR','CLAIM_SUBMISSION','SUSPECT_NOTICE','OTHER')),
  type_confidence REAL NOT NULL CHECK (type_confidence >= 0 AND type_confidence <= 1),
  fields TEXT NOT NULL CHECK (json_valid(fields)),
  field_confidence TEXT NOT NULL CHECK (json_valid(field_confidence)),
  field_source TEXT CHECK (field_source IS NULL OR json_valid(field_source)),
  raw_text_ref TEXT,
  language_detected TEXT,
  supersedes TEXT REFERENCES interpretations(interp_id),
  created_at TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_interp_evidence ON interpretations(evidence_id);

CREATE TABLE IF NOT EXISTS relationships (
  rel_id TEXT PRIMARY KEY,
  from_id TEXT NOT NULL,
  to_id TEXT,
  type TEXT NOT NULL CHECK (type IN ('EXACT','INFERRED','MANUAL','UNMATCHED')),
  basis TEXT NOT NULL CHECK (json_valid(basis)),
  score REAL CHECK (score IS NULL OR (score >= 0 AND score <= 1)),
  reason TEXT NOT NULL,
  created_by TEXT NOT NULL,
  supersedes TEXT REFERENCES relationships(rel_id),
  created_at TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_id);
CREATE INDEX IF NOT EXISTS idx_rel_to ON relationships(to_id);

CREATE TABLE IF NOT EXISTS decisions (
  dec_id TEXT PRIMARY KEY,
  subject_ref TEXT NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('approved','rejected','proof_requested','manual_link')),
  decided_by TEXT NOT NULL,
  reason TEXT NOT NULL,
  seen_snapshot_hash TEXT NOT NULL,
  supersedes TEXT REFERENCES decisions(dec_id),
  created_at TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_dec_subject ON decisions(subject_ref);

-- Reserved for Day 4 (B5). Versioned rows: a case change is a new row.
CREATE TABLE IF NOT EXISTS cases (
  case_row_id TEXT PRIMARY KEY,
  case_ref TEXT NOT NULL,
  trip_id TEXT NOT NULL REFERENCES trips(trip_id),
  state TEXT NOT NULL,
  evidence_refs TEXT NOT NULL CHECK (json_valid(evidence_refs)),
  opened_at TEXT NOT NULL,
  last_action TEXT,
  created_at TEXT NOT NULL,
  supersedes TEXT REFERENCES cases(case_row_id)
);

-- Day 2-7 additions. All append-only; a change is a new row that supersedes the old one.
CREATE TABLE IF NOT EXISTS join_codes (
  code TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(trip_id),
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);

-- Labelled self-reports ("traveller asserts travel"). Never machine-produced states.
CREATE TABLE IF NOT EXISTS assertions (
  assertion_id TEXT PRIMARY KEY,
  trip_id TEXT NOT NULL REFERENCES trips(trip_id),
  sender_id TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('traveller_asserts_travel')),
  subject_ref TEXT,
  created_at TEXT NOT NULL
);

-- Adaptive evidence challenges. status: issued -> responded | no_response (never 'rejected').
CREATE TABLE IF NOT EXISTS challenges (
  challenge_id TEXT PRIMARY KEY,
  subject_ref TEXT NOT NULL,
  trip_id TEXT,
  attribute TEXT NOT NULL,
  request_type TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  message TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('issued','responded','no_response')),
  due_at TEXT NOT NULL,
  response_evidence_id TEXT,
  created_at TEXT NOT NULL,
  supersedes TEXT REFERENCES challenges(challenge_id)
);
CREATE INDEX IF NOT EXISTS idx_chal_subject ON challenges(subject_ref);

CREATE TABLE IF NOT EXISTS audit_chain (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  record_type TEXT NOT NULL,
  record_id TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  record_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  UNIQUE (record_type, record_id)
);

CREATE TABLE IF NOT EXISTS access_log (
  log_id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  subject_ref TEXT,
  reason TEXT NOT NULL,
  at TEXT NOT NULL
);
"""


def trigger_sql() -> str:
    parts = []
    for t in APPEND_ONLY_TABLES:
        for op in ("UPDATE", "DELETE"):
            parts.append(
                f"CREATE TRIGGER IF NOT EXISTS trg_{t}_no_{op.lower()} BEFORE {op} ON {t} "
                f"BEGIN SELECT RAISE(ABORT, 'append-only: {op} is forbidden on {t}'); END;")
    return "\n".join(parts)


def trigger_names() -> list:
    return [f"trg_{t}_no_{op}" for t in APPEND_ONLY_TABLES for op in ("update", "delete")]
