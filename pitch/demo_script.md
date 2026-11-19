# Three-minute demo and judge Q&A

This script uses the local synthetic dashboard. It does not claim that the current fixtures are model output or measured performance.

## Demo run

### 0:00–0:20 · Set the boundary

“Pratibimb helps a coordinator organize travel screenshots after they are sent. A screenshot is a claim. We separate what was sent, what was read, why items were linked and what a human decided.”

### 0:20–0:45 · Trip overview

Open the held-out synthetic trip. Point out the roster and the review count. Name the fixture label and explain that these are hand-authored examples, not real travellers or model results.

### 0:45–1:15 · Exceptions inbox

Open “Pending payment; no ticket evidence.” Read the reason and show the attribute-level labels. Explain that the case stays open for a coordinator; the system does not infer ticket issuance from a payment attempt.

### 1:15–1:45 · Evidence trail

Open an item and move through Evidence, Interpretation, Relationship and Decision. Explicitly distinguish the synthetic ground-truth fields from model output. Use “View synthetic screenshot” only if asked to see the source image.

### 1:45–2:05 · Claim sheet

Download CSV or XLSX. Point to the relationship type, evidence level by attribute and reason columns. Show that INFERRED, MANUAL and UNMATCHED remain visible.

### 2:05–2:35 · Break-me station

Show the crop, duplicate, out-of-window, pending-payment and suspicious-message fixtures. The page shows expected fixture handling; no live classifier is connected in this local build. Do not call these model catches.

### 2:35–3:00 · Audit check

Change a synthetic chain record, show the first mismatch, then reset the fixture. Explain that the hash chain provides evidence of an edit; it does not prevent one.

## Judge Q&A

**Does this establish that the traveller rode?**

No. Travel is the traveller’s assertion; this system organizes submitted evidence and coordinator decisions. It cannot see gate scans.

**Could two fabricated screenshots agree?**

Yes. Corroboration means the sources agree on an attribute. An external authority would be needed to confirm that specific fact independently.

**What if there is no shared identifier?**

The relationship can be INFERRED, but it stays with the coordinator for review. If candidates conflict or evidence is missing, preserve it as UNMATCHED.

**What performance have you measured?**

None yet. The current 30-item corpus is synthetic. The evaluation harness is ready for real model outputs, and the interview and timing templates are blank.

**How do you handle privacy?**

The coordinator view uses fields rather than showing images by default. In this local fixture app, image reveals are synthetic and logged in memory. Production raw-image access still needs B’s logged endpoint and a retention policy.

**Why use Sarvam?**

The design uses Sarvam for Indian-language extraction and reply translation. The Day-0 screenshot test must establish whether the proposed extraction flow works on real screens.

## Do not claim

- That a real coordinator has been interviewed or that coordinator time has decreased.
- Extraction accuracy, false-accept rate, coverage or model resistance from the synthetic corpus.
- That the current browser fixture is connected to Member A’s classifier or Member B’s ledger.
- That a ticket screenshot confirms travel.
