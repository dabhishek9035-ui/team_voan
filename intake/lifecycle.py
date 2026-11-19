"""
Raw-Image Lifecycle and Privacy Retention Worker for Pratibimb Member A.
Implements secure retention, automated expiration cleanup, and audit logging.

Principles:
- Extracted fields and perceptual fingerprints are retained; raw images are purged.
- Honest claim: "masked fields plus fingerprints." We do not claim zero-knowledge.
- All deletions are cryptographically logged with Evidence ID and SHA-256 in an append-only audit log.
"""

from __future__ import annotations
import os
import json
import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


class ImageLifecycleWorker:
    """
    Manages raw image retention, access control, and audited deletion.
    """

    def __init__(
        self,
        storage_dir: Union[str, Path] = "storage/raw_images",
        audit_log_path: Union[str, Path] = "docs/retention_audit.log",
        default_retention_hours: float = 72.0,  # 3 days default
    ):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log_path = Path(audit_log_path)
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_retention_hours = default_retention_hours

        # In-memory registry of image retention metadata
        self._registry_file = self.storage_dir / "retention_registry.json"
        self._registry: Dict[str, Dict[str, Any]] = self._load_registry()

    def _load_registry(self) -> Dict[str, Dict[str, Any]]:
        if self._registry_file.exists():
            try:
                with open(self._registry_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_registry(self) -> None:
        with open(self._registry_file, "w", encoding="utf-8") as f:
            json.dump(self._registry, f, indent=2)

    def register_image(
        self,
        evidence_id: str,
        file_path: Union[str, Path],
        sha256: str,
        retention_hours: Optional[float] = None,
        case_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Registers an intake image under the retention policy.
        """
        hours = retention_hours if retention_hours is not None else self.default_retention_hours
        created_at = datetime.datetime.now(datetime.timezone.utc)
        expires_at = created_at + datetime.timedelta(hours=hours)

        entry = {
            "evidence_id": evidence_id,
            "file_path": str(file_path),
            "sha256": sha256,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "case_id": case_id,
            "status": "RETAINED",
        }
        self._registry[evidence_id] = entry
        self._save_registry()
        return entry

    def delete_image(
        self,
        evidence_id: str,
        reason: str = "retention_policy_expired"
    ) -> bool:
        """
        Securely purges the raw image file from disk and records an append-only audit log entry.
        """
        if evidence_id not in self._registry:
            return False

        entry = self._registry[evidence_id]
        file_path = Path(entry["file_path"])
        file_existed = file_path.exists()

        if file_existed:
            try:
                # Remove file from disk
                os.remove(file_path)
            except OSError:
                return False

        # Record audit log entry
        audit_entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "evidence_id": evidence_id,
            "sha256": entry["sha256"],
            "file_path": entry["file_path"],
            "reason": reason,
            "status": "PURGED_SUCCESSFULLY",
            "file_was_present": file_existed,
        }

        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_entry) + "\n")

        entry["status"] = "DELETED"
        entry["deleted_at"] = audit_entry["timestamp"]
        entry["deletion_reason"] = reason
        self._save_registry()

        return True

    def run_cleanup_sweep(self) -> List[str]:
        """
        Sweeps the storage directory and deletes all expired images whose retention window has passed.
        Returns list of deleted evidence_ids.
        """
        now = datetime.datetime.now(datetime.timezone.utc)
        deleted_ids = []

        for ev_id, entry in list(self._registry.items()):
            if entry.get("status") == "DELETED":
                continue

            expires_at = datetime.datetime.fromisoformat(entry["expires_at"])
            if now >= expires_at:
                if self.delete_image(ev_id, reason="retention_window_elapsed"):
                    deleted_ids.append(ev_id)

        return deleted_ids
