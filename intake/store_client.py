"""
Store Client Interface for Pratibimb Member A.
Abstracts communication with Member B's append-only store.
Supports direct in-process `pratibimb.Store`, HTTP API calls, and an in-memory fallback store.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from intake.models import EvidenceRecord, InterpretationRecord

load_dotenv()

VALID_FIELD_SOURCES = ("sarvam_extract", "sarvam_digitise", "qr_decoder", "llm_structuring")


def _prepare_evidence_payload(evidence: EvidenceRecord) -> Dict[str, Any]:
    data = evidence.model_dump()
    if data.get("status") not in ("received", "quarantined"):
        data["status"] = "received"
    return data


def _prepare_interpretation_payload(interpretation: InterpretationRecord) -> Dict[str, Any]:
    data = interpretation.model_dump()
    iid = data.get("interp_id", "")
    if iid.startswith("int_"):
        iid = "in_" + iid[4:]
        data["interp_id"] = iid

    fields = dict(data.get("fields") or {})
    conf = dict(data.get("field_confidence") or {})
    src = dict(data.get("field_sources") or {})
    clean_conf: Dict[str, float] = {}
    clean_src: Dict[str, Optional[str]] = {}

    for key, val in fields.items():
        if val is None:
            clean_conf[key] = 0.0
            clean_src[key] = None
        else:
            c = conf.get(key, 0.9)
            clean_conf[key] = float(c) if c and float(c) > 0.0 else 0.9
            s = src.get(key)
            clean_src[key] = s if s in VALID_FIELD_SOURCES else "sarvam_digitise"

    data["fields"] = fields
    data["field_confidence"] = clean_conf
    data["field_source"] = clean_src
    return data


class StoreClient:
    """
    Client for Member B's store.
    Section 1.4 contract:
      store.add_evidence(...) -> returns evidence_id
      store.add_interpretation(...) -> returns interp_id
      GET /trips/{id}/summary -> trip data
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        offline: bool = False,
        timeout: float = 1.0,
        store: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        resolved_url = base_url if base_url is not None else os.getenv("CORE_API_URL", "http://localhost:8000")
        self.base_url = resolved_url.rstrip("/") if resolved_url else None
        self.store = store
        self.config = config
        self.offline = offline
        self.timeout = timeout
        # In-memory store used during offline testing or when Member B is not running
        self._in_memory_evidence: Dict[str, EvidenceRecord] = {}
        self._in_memory_interpretations: Dict[str, InterpretationRecord] = {}
        self._trip_join_codes: Dict[str, str] = {"METRO2026": "trip_bengaluru_fest_01"}

    def _ensure_trip_and_traveller(self, trip_id: Optional[str], sender_id: str) -> None:
        if not trip_id or self.store is None:
            return
        try:
            self.store.get_trip(trip_id)
        except Exception:
            self.store.add_trip(name=trip_id, coordinator_id="coordinator:system", trip_id=trip_id)
        existing = {t["sender_id"] for t in self.store.list_travellers(trip_id)}
        if sender_id not in existing:
            self.store.add_traveller(trip_id, sender_id, label=sender_id)

    def add_evidence(self, evidence: EvidenceRecord) -> str:
        """Saves Evidence record to Member B's store."""
        payload = _prepare_evidence_payload(evidence)
        if self.store is not None:
            self._ensure_trip_and_traveller(payload.get("trip_id"), payload["sender_id"])
            return self.store.add_evidence(
                sender_id=payload["sender_id"],
                channel=payload["channel"],
                received_at=payload["received_at"],
                sha256=payload["sha256"],
                phash=payload.get("phash"),
                ahash=payload.get("ahash"),
                file_ref=payload.get("file_ref"),
                trip_id=payload.get("trip_id"),
                status=payload.get("status", "received"),
                evidence_id=payload["evidence_id"],
            )

        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/records/evidence",
                        json=payload,
                    )
                    if resp.status_code in (200, 201):
                        return resp.json().get("evidence_id", evidence.evidence_id)
            except Exception:
                pass

        # In-memory fallback store
        self._in_memory_evidence[evidence.evidence_id] = evidence
        return evidence.evidence_id

    def add_interpretation(self, interpretation: InterpretationRecord) -> str:
        """Saves Interpretation record to Member B's store."""
        payload = _prepare_interpretation_payload(interpretation)
        if self.store is not None:
            from pratibimb import cases, challenge, linking
            from pratibimb.config import load_config

            cfg = self.config or load_config()
            iid = self.store.add_interpretation(
                evidence_id=payload["evidence_id"],
                producer=payload["producer"],
                model_version=payload["model_version"],
                screenshot_type=payload["screenshot_type"].value
                if hasattr(payload["screenshot_type"], "value")
                else payload["screenshot_type"],
                type_confidence=payload["type_confidence"],
                fields=payload["fields"],
                field_confidence=payload["field_confidence"],
                field_source=payload["field_source"],
                sarvam_job_id=payload.get("sarvam_job_id"),
                raw_text_ref=payload.get("raw_text_ref"),
                language_detected=payload.get("language_detected"),
                supersedes=payload.get("supersedes"),
                interp_id=payload["interp_id"],
            )
            linking.link_interpretation(self.store, iid, cfg)
            ev = self.store.get(payload["evidence_id"])
            if ev.get("trip_id"):
                cases.reconcile(self.store, ev["trip_id"], cfg)
                cases.sync_cases(self.store, ev["trip_id"], cfg)
                challenge.auto_respond(self.store, ev["trip_id"], cfg)
            return iid

        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/records/interpretation",
                        json=payload,
                    )
                    if resp.status_code in (200, 201):
                        return resp.json().get("interp_id", payload["interp_id"])
            except Exception:
                pass

        # In-memory fallback store
        self._in_memory_interpretations[interpretation.interp_id] = interpretation
        return interpretation.interp_id

    def lookup_trip_by_join_code(self, join_code: str) -> Optional[str]:
        """Resolves trip_id from coordinator's join code."""
        code = join_code.strip().upper()
        if self.store is not None:
            row = self.store.get_join_code(code)
            if row:
                return row["trip_id"]

        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(f"{self.base_url}/trips/lookup?join_code={code}")
                    if resp.status_code == 200:
                        return resp.json().get("trip_id")
            except Exception:
                pass
        return self._trip_join_codes.get(code)

    def get_trip_summary(self, trip_id: str) -> Optional[Dict[str, Any]]:
        """Fetches trip summary from Member B (GET /trips/{id}/summary)."""
        if self.store is not None:
            from pratibimb import claims, trust
            from pratibimb.config import load_config

            cfg = self.config or load_config()
            trip = self.store.get_trip(trip_id)
            built = claims.build_claims(self.store, trip_id, cfg)
            out_claims = []
            for c in built:
                c.update(trust.assess(self.store, c, cfg, trip))
                out_claims.append(claims.public(c))
            return {"trip_id": trip_id, "trip": trip, "travellers": self.store.list_travellers(trip_id), "claims": out_claims}

        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(f"{self.base_url}/trips/{trip_id}/summary")
                    if resp.status_code == 200:
                        return resp.json()
            except Exception:
                pass
        return None

    def trigger_challenge(self, subject_id: str, trip_id: str) -> Optional[Dict[str, Any]]:
        """Triggers an adaptive evidence challenge via Member B (POST /challenge/{id})."""
        if self.store is not None:
            from pratibimb import challenge
            from pratibimb.config import load_config

            cfg = self.config or load_config()
            return challenge.issue(self.store, trip_id, subject_id, cfg)

        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/challenge/{subject_id}",
                        json={"trip_id": trip_id},
                    )
                    if resp.status_code in (200, 201):
                        return resp.json()
            except Exception:
                pass
        return None
