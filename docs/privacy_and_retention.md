# B8: Privacy, Masking and Retention (Member B)

Implemented in [`pratibimb/privacy.py`](../pratibimb/privacy.py) and exposed via [`pratibimb/api.py`](../pratibimb/api.py).

## 1. Honest Wording
Pratibimb does **not** claim "zero knowledge." The honest description is **"masked fields plus fingerprints"**:
- Extracted fields, SHA-256 hashes, perceptual fingerprints (`phash`, `ahash`), extraction confidences, relationships, and decisions are retained in the append-only store.
- Raw screenshot images are **never** returned by default on coordinator APIs (`/trips/{id}/summary`, `/trips/{id}/inbox`, `/records/{id}/trail`, `/export/claims`).

## 2. What Is Stored, Why, How Long, and Who Can See It
| Data | Why | How Long | Who Can See It |
|---|---|---|---|
| **Masked fields** (`payer_name_masked`, `payee_name`, `utr`, `order_id`, `ticket_id`, `qr_payload`) | Coordinator exception review and reimbursement export | Retained in append-only `interpretations` | Coordinator API returns masked views (`privacy.mask_fields`, `privacy.view_interpretation`) with phone numbers hidden (`[phone hidden]`) |
| **Full field values** | Required only after a human Decision exists on the item | Same as interpretation | Coordinator only via `privacy.reveal_fields` (requires `coordinator:*` actor, non-empty reason, and an existing `Decision`; logged to `access_log`) |
| **Cryptographic & perceptual fingerprints** (`sha256`, `phash`, `ahash`) | Three-layer duplicate detection without keeping images | Retained in append-only `evidence` | Core engine and coordinator summary flags |
| **Raw screenshot images** (`file_ref`) | Optional visual inspection during disputes | Encrypted/restricted until the claim is closed by a human decision OR `raw_image_retention_days` (default 30 days) elapses; confirm final period with privacy/legal reviewer | Excluded from `privacy.view_evidence` (`file_ref = None`); explicit access via `POST /raw-image/{evidence_id}` (`privacy.request_raw_image`) requires `coordinator:*` and a reason, and writes `raw_image_request` / `raw_image_served` to `access_log` |

## 3. Audited Deletion (`retention_sweep`)
- `privacy.retention_sweep(store, cfg)` removes raw image files on disk when a claim is resolved by a human Decision or when `raw_image_retention_days` elapses.
- Because the four core record tables (`evidence`, `interpretations`, `relationships`, `decisions`) are strictly append-only, deletion records an entry in `access_log` (`actor = "system:retention"`, `action = "raw_image_deleted"`, `subject_ref = evidence_id`, `reason = ...`).
- Subsequent `POST /raw-image/{evidence_id}` calls log the request and return `400 Bad Request` / `NotFoundError` stating that the raw image was deleted under the retention rule while fields and fingerprints remain.
