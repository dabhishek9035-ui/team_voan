# C1/C5: Baseline timing protocol (metric 3)

Compare a human doing the coordinator's job **manually** against the same job **with Pratibimb**, on the **same** set.

1. Fix a set (e.g. 40 screenshots from the held-out split, with known duplicates, a no-ticket payment, an out-of-window ride).
2. Manual run: participant sees screenshots in a chat-like scroll plus a spreadsheet; task = produce the claim list and flag problems.
   Record seconds, errors (wrong decisions) and missed duplicates.
3. Pratibimb run: different participant (or same after a gap, counterbalanced) uses the inbox only.
4. >= 3 participants per condition if possible. Report n and median, not a single run.
5. Record in `eval/data/timing.csv` (template: `eval/data/timing_template.csv`). The harness reports medians and the ratio.

Caveat to state: small n, participants who know the system, set chosen by us.
