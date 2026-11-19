# Pratibimb Privacy and Retention Architecture
**Author:** Member A (Intake, Extraction and Reply)  
**Scope:** Raw Screenshot Ingestion, Transit to AI Providers, Masking, and Lifecycle Purging  

---

## 1. Privacy Principles & Realistic Claims

1. **Honest Wording:** Pratibimb operates under the principle of **"Masked fields plus perceptual fingerprints."** We do not claim "zero-knowledge encryption" or "instant client-side zero trust," because phone screenshots are transmitted by travellers over Telegram/WhatsApp and processed via Sarvam Document AI before structured fields are extracted.
2. **Access Control:** The coordinator dashboard, exceptions inbox, and export sheets **never show raw screenshot images** by default. They display structured, corroborated fields with sensitive elements masked:
   - Payer Names: `Meera Krishnan` $\to$ `M***a K******n`
   - UPI UTRs / Bank Accounts: `401928374615` $\to$ `4019****4615`
   - Phone Numbers: Completely omitted from public views.
3. **Audit Trails for Raw Image Access:** If an administrative reviewer or fraud investigator requires visual inspection of a disputed raw screenshot, an explicit audit request is generated (`GET /records/{id}/image?reason=dispute_investigation`). The audit log permanently records `user_id`, `timestamp`, `ip_address`, and `justification_reason`.

---

## 2. Third-Party Provider Transit (Sarvam AI)

- Screenshots sent to Pratibimb are ingested by Member A's intake pipeline and dispatched via HTTPS/TLS to **Sarvam AI** Document AI (`https://api.sarvam.ai/document/digitise` and `/extract`).
- **Residency:** Sarvam AI’s processing infrastructure resides in Indian data centers, aligning with RBI and Indian Digital Personal Data Protection (DPDP) Act requirements for financial transaction processing.
- **Provider Retention:** In compliance with enterprise developer terms, images submitted via the inference API are not retained for model training without explicit enterprise opt-in. Once digitised, the structured response is returned and local storage takes ownership.

---

## 3. Raw-Image Lifecycle & Automated Purging

The `ImageLifecycleWorker` (`intake/lifecycle.py`) implements automated data hygiene:
1. **Quarantine & Ingestion:**
   Upon intake, the raw image file is assigned a cryptographic identifier (`evidence_id = ev_<hex>`), its SHA-256 and perceptual hashes (`pHash`, `aHash`) are computed, and the file is stored in a private directory with restricted permissions.
2. **Retention Policy Windows:**
   - **Default Window:** 72 hours from intake for standard claims.
   - **Exception Cases (debited without ticket):** Kept until case resolution or up to 14 days (covering the BMRCL 7-business-day refund window).
3. **Audited Deletion:**
   When the retention period expires or when the coordinator marks a case resolved, the `ImageLifecycleWorker.delete_image(...)` executes an unrecoverable file deletion.
   Every purge event is appended to `docs/retention_audit.log` recording:
   - `timestamp`
   - `evidence_id`
   - `sha256`
   - `reason` (e.g. `retention_window_elapsed`, `case_resolved`)
   - `status`: `PURGED_SUCCESSFULLY`
4. **Permanent Artifacts:**
   After the raw image is purged, Pratibimb permanently retains only:
   - Extracted normalized fields (amounts, stations, masked identifiers)
   - SHA-256 and pHash/aHash fingerprints
   - Hash-chained audit records of relationships and decisions
