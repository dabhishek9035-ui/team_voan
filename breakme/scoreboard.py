"""Break-me scoreboard: append-only JSONL log. Attempts that got through are kept on purpose."""
import json
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).with_name("attempts.jsonl")


def log(who, what, system_said, outcome):
    rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "who": who, "sent": what,
           "system_said": system_said, "outcome": outcome}
    with open(LOG, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_all():
    return [json.loads(l) for l in open(LOG)] if LOG.exists() else []


def summary():
    rows = read_all()
    return {"total": len(rows),
            "caught": sum(r["outcome"].startswith("caught") for r in rows),
            "got_through": sum(r["outcome"] == "got through" for r in rows),
            "unreadable": sum(r["outcome"] == "could not read" for r in rows)}
