# Judge Q&A to rehearse

| Question | Prepared answer |
|---|---|
| "Isn't a screenshot never proof?" | Correct. The screenshot is the claim. We establish ownership, relationships and consistency, and label how well each claim is supported. We never say "verified" unless an authoritative source confirmed that specific attribute. |
| "AI fakes have no edit artifacts." | We don't rely on pixels. We rely on evidence relationships, an adaptive evidence challenge, and human review. Here is where fakes still get through (show the where-it-fails table). |
| "Two fake screenshots can agree with each other." | Yes. That is why "corroborated" means consistent, not true, and why the top level needs an external source for that attribute. |
| "What if there is no shared ID?" | Links are INFERRED: never auto-cleared, always reviewed, marked in the export. |
| "Why Sarvam?" | Indian-language screens and messages, plus translating reasons into the traveller's language. |
| "Privacy?" | Coordinator sees fields, not images. Fingerprints for duplicate checks. Raw images deleted per a retention rule. We say "masked fields plus fingerprints", not zero knowledge. |
| "Can it issue refunds or confirm travel?" | No. It structures evidence, tracks cases and records decisions. Travel is the traveller's assertion. |
| "Why not just use the metro app?" | The app issues tickets. We handle what happens after: who has what, what failed, who gets paid. |
| "How many screenshots did you test?" | State n from the run, split, and how many were real vs synthetic. If small, say so first. |
| "Do duplicate screenshots get caught by image hashes?" | Exact resends yes. Cropped and recompressed copies are similar, but hashes also match unrelated screens that share a template, so we gate them behind the ticket ID. A screenshot of a screenshot is caught only by the ID. See eval/results/fingerprint_check.json. |
| "Your demo data is synthetic." | Yes, and labelled. It checks plumbing and edge cases. Accuracy numbers come only from real consented screenshots, with n stated. |
