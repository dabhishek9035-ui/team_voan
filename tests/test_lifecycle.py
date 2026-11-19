"""
Unit tests for Raw-Image Lifecycle and Privacy Retention Worker.
"""

from pathlib import Path
from intake.lifecycle import ImageLifecycleWorker


def test_lifecycle_image_registration_and_deletion(tmp_path):
    storage_dir = tmp_path / "raw_storage"
    audit_log = tmp_path / "test_audit.log"

    worker = ImageLifecycleWorker(
        storage_dir=storage_dir,
        audit_log_path=audit_log,
        default_retention_hours=1.0,
    )

    # Create dummy test image file
    test_file = storage_dir / "test_img_01.png"
    test_file.write_bytes(b"\x89PNG\r\n\x1a\nfakeimagebytes")
    assert test_file.exists()

    # Register under retention policy
    entry = worker.register_image(
        evidence_id="ev_test_101",
        file_path=test_file,
        sha256="fake_sha256_hash",
        retention_hours=0.0001,  # immediate expiration
    )
    assert entry["status"] == "RETAINED"

    # Delete image explicitly
    success = worker.delete_image("ev_test_101", reason="case_resolved")
    assert success is True

    # VERIFY FILE IS ACTUALLY DELETED FROM DISK
    assert not test_file.exists()

    # VERIFY AUDIT LOG ENTRY WRITTEN
    assert audit_log.exists()
    log_content = audit_log.read_text(encoding="utf-8")
    assert "ev_test_101" in log_content
    assert "PURGED_SUCCESSFULLY" in log_content
    assert "case_resolved" in log_content


def test_lifecycle_cleanup_sweep(tmp_path):
    storage_dir = tmp_path / "raw_storage_sweep"
    audit_log = tmp_path / "sweep_audit.log"

    worker = ImageLifecycleWorker(
        storage_dir=storage_dir,
        audit_log_path=audit_log,
    )

    # Register an already expired file
    expired_file = storage_dir / "expired.png"
    expired_file.write_bytes(b"data")
    worker.register_image(
        evidence_id="ev_expired_99",
        file_path=expired_file,
        sha256="hash99",
        retention_hours=-1.0,  # expired 1 hour ago
    )

    # Run cleanup sweep
    deleted_ids = worker.run_cleanup_sweep()
    assert "ev_expired_99" in deleted_ids
    assert not expired_file.exists()
