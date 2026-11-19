"""
Store Client Interface for Pratibimb Member A.
Abstracts communication with Member B's append-only store.
Supports both direct HTTP API calls and an in-memory test store.
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
import httpx
from intake.models import EvidenceRecord, InterpretationRecord


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
        base_url: Optional[str] = "http://localhost:8000",
        offline: bool = False,
        timeout: float = 0.5,
    ):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.offline = offline or (base_url is None)
        self.timeout = timeout
        # In-memory store used during offline testing or when Member B is not running
        self._in_memory_evidence: Dict[str, EvidenceRecord] = {}
        self._in_memory_interpretations: Dict[str, InterpretationRecord] = {}
        self._trip_join_codes: Dict[str, str] = {"METRO2026": "trip_bengaluru_fest_01"}

    def add_evidence(self, evidence: EvidenceRecord) -> str:
        """Saves Evidence record to Member B's store."""
        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/records/evidence",
                        json=evidence.model_dump(),
                    )
                    if resp.status_code == 200:
                        return resp.json().get("evidence_id", evidence.evidence_id)
            except Exception:
                pass

        # In-memory store
        self._in_memory_evidence[evidence.evidence_id] = evidence
        return evidence.evidence_id

    def add_interpretation(self, interpretation: InterpretationRecord) -> str:
        """Saves Interpretation record to Member B's store."""
        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        f"{self.base_url}/records/interpretation",
                        json=interpretation.model_dump(),
                    )
                    if resp.status_code == 200:
                        return resp.json().get("interp_id", interpretation.interp_id)
            except Exception:
                pass

        # In-memory store
        self._in_memory_interpretations[interpretation.interp_id] = interpretation
        return interpretation.interp_id

    def lookup_trip_by_join_code(self, join_code: str) -> Optional[str]:
        """Resolves trip_id from coordinator's join code."""
        if not self.offline and self.base_url:
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.get(f"{self.base_url}/trips/lookup?join_code={join_code}")
                    if resp.status_code == 200:
                        return resp.json().get("trip_id")
            except Exception:
                pass
        return self._trip_join_codes.get(join_code.strip().upper())
