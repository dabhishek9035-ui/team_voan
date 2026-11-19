# Pratibimb Threat Model & Boundary of Claims
**Component:** Intake, Extraction, Fingerprinting and Reply Channel  
**Author:** Member A (Intake and Extraction)  

---

## 1. What Pratibimb Does and Does Not Claim

> **Pratibimb does not establish truth. It establishes ownership, evidence relationships, consistency and accountability.**

- A screenshot is a **claim**, not proof.
- Two fabricated screenshots can agree with each other; therefore, corroboration means *consistent*, not *true*.
- The product never says "fraud" and never says "verified" unless an authoritative source confirmed that specific attribute. It says *extracted*, *corroborated*, *unverified*, *needs review*.
- "Travelled" is the traveller's assertion; we cannot see physical AFC metro gate scans. "Approved" is a human coordinator's decision.

---

## 2. Threat Vectors & Intake Defenses

| Threat Vector | Attacker Action | System Defense | Limitation / Failure Boundary |
|---|---|---|---|
| **Exact Resend** | Traveller resubmits the exact same ticket image twice to get double reimbursement. | `Evidence.sha256` matching identifies identical file immediately. | Trivial to defeat by cropping 1 pixel or recompressing. |
| **Cropped / Recompressed Reuse** | Attacker re-saves or crops an already-submitted ticket to change the file hash. | `pHash` and `aHash` perceptual fingerprints detect visual similarity within Hamming distance threshold ($\le 6$). | Does not distinguish between two legitimate tickets with near-identical layout if stations and fares are identical; human review required. |
| **Cross-Sender Replay** | Traveller B submits a screenshot borrowed from Traveller A. | Normalised `ticket_id`, `utr`, and `qr_payload` semantic duplicates trigger cross-sender alert. | If the ticket ID was intentionally blurred or obscured, semantic matching fails $\to$ falls back to perceptual similarity. |
| **Hallucinated LLM Fields** | Extraction model invents a convincing 12-digit UTR on a degraded image. | **Hallucination Guardrail:** `validate_hallucinations` enforces that every non-null field must occur in raw digitised OCR text or be marked null with confidence 0.0. | OCR error in a single digit still requires fuzzy OCR normalisation logging. |
| **Phishing / Refund Scams** | Scammer sends a fake text or screenshot claiming refund failure to trick traveller or coordinator. | Classifier recognizes `SUSPECT_NOTICE` patterns (unauthorized APKs, AnyDesk, suspicious payment links) and quarantines claim. | Novel phishing wording may drop to `OTHER`, which safely abstains from auto-clearing. |
| **Fully Synthetic Set (AI-Generated Receipt + SMS)** | Sophisticated actor uses generative AI or image editor to create matching UPI and ticket screens. | **Adaptive Evidence Challenge:** System asks for an orthogonal third source (e.g., bank statement or transaction timeline). | If the attacker fakes all three consistent items, Pratibimb labels them "Corroborated, Unverified". It does not detect perfect deepfakes without external bank API confirmation. |
| **Tampering with Past Evidence** | Rogue administrator attempts to edit ticket amount in the database. | Member B's append-only hash chain (`record_hash = H(record + prev_hash)`) breaks audit verification immediately. | Hash-chain provides tamper *evidence*, not physical tamper prevention. |

---

## 3. The Adaptive Evidence Challenge Threat Model

When an intake item cannot be cleanly linked or exhibits anomalies:
1. The system **never auto-rejects** on suspicion alone.
2. It generates an **Adaptive Evidence Challenge** reply card (`NEEDS_MORE_EVIDENCE`), specifying the exact unresolved attribute (e.g. "UTR missing or unreadable").
3. It asks for the smallest corroborating item that would conflict with a fabricated claim:
   - Bank SMS debit notification.
   - Payment app transaction history list showing the status bar and timestamp.
4. If the traveller cannot or does not provide it, the claim remains **"corroborated, unverified"** and is escalated to the coordinator with explicit reasons.
