"""
Forbidden-words lint (brief section 0.5): the product's OUTPUT may not say "fraud", "verified" or "proof".
Allowed: 'independently verified' (only when an authoritative source confirmed that attribute),
the decision action 'request proof' / proof_requested, and lines that quote the rule itself.

  python tools/check_forbidden.py [paths...]      exit 1 if anything is found
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ["dashboard", "export", "breakme", "standin", "eval/make_predictions_standin.py", "docs/data_notes.md", "docs/deck_outline.md", "docs/demo_script.md", "docs/judge_qa.md"]
BAD = re.compile(r"\b(fraud\w*|verified|proof)\b", re.I)
OK = re.compile(r"independently[ _]verified|request proof|proof[ _]requested|\bnever\b|\bunless\b|forbidden|check_forbidden|not proof|isn't proof", re.I)


def scan(paths):
    hits = []
    for p in paths:
        p = ROOT / p
        files = [p] if p.is_file() else [f for f in p.rglob("*") if f.suffix in (".py", ".md", ".txt", ".html")]
        for f in files:
            for n, line in enumerate(f.read_text(errors="ignore").splitlines(), 1):
                if BAD.search(line) and not OK.search(line):
                    hits.append(f"{f.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    return hits


if __name__ == "__main__":
    hits = scan(sys.argv[1:] or DEFAULT)
    print("\n".join(hits) if hits else "forbidden-words check: clean")
    sys.exit(1 if hits else 0)
