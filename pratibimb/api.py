"""Small dependency-free WSGI adapter for the B8 store and claim engine."""
import json
from urllib.parse import parse_qs, urlparse

from . import challenge, claims, privacy
from .config import load_config


def _reply(start_response, status, payload):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(status, [("Content-Type", "application/json"),
                            ("Content-Length", str(len(body)))])
    return [body]


def create_app(store, config=None):
    cfg = config or load_config()

    def app(environ, start_response):
        parsed = urlparse(environ.get("RAW_URI", environ.get("PATH_INFO", "")))
        parts = [part for part in parsed.path.split("/") if part]
        method = environ.get("REQUEST_METHOD", "GET")
        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ.get("wsgi.input")
        payload = json.loads(raw.read(length) or b"{}") if length and raw else {}
        try:
            if method == "POST" and parts == ["trips"]:
                trip_id = store.add_trip(payload["name"], payload["coordinator_id"],
                                         window_start=payload.get("window_start"),
                                         window_end=payload.get("window_end"))
                return _reply(start_response, "201 Created", {"trip_id": trip_id})
            if method == "POST" and len(parts) == 3 and parts[0] == "trips" and parts[2] == "join-code":
                result = store.add_join_code(parts[1], payload.get("created_by", "coordinator:api"),
                                             ttl_hours=payload.get("ttl_hours", cfg["join_code_ttl_hours"]))
                return _reply(start_response, "201 Created", result)
            if method == "POST" and parts == ["decisions"]:
                return _reply(start_response, "201 Created",
                              {"dec_id": store.add_decision(**payload)})
            if method == "POST" and len(parts) == 2 and parts[0] == "challenge":
                result = challenge.issue(store, payload["trip_id"], parts[1], cfg)
                return _reply(start_response, "201 Created", result)
            if method == "POST" and len(parts) == 2 and parts[0] == "challenge-response":
                challenge.respond(store, parts[1], payload["evidence_id"])
                return _reply(start_response, "200 OK", {"challenge_id": parts[1], "status": "responded"})
            if method == "POST" and len(parts) == 2 and parts[0] == "raw-image":
                path = privacy.request_raw_image(store, parts[1], payload["actor"],
                                                 payload["reason"], cfg)
                return _reply(start_response, "200 OK", {"evidence_id": parts[1], "path": path})
            if method == "GET" and parts == ["audit", "verify"]:
                return _reply(start_response, "200 OK", store.verify())
            if method == "GET" and len(parts) == 3 and parts[0] == "trips" and parts[2] in ("summary", "inbox"):
                result = {"trip_id": parts[1], "travellers": store.list_travellers(parts[1]),
                          "claims": [claims.public(c) for c in claims.build_claims(store, parts[1], cfg)]}
                if parts[2] == "inbox":
                    result["claims"] = [c for c in result["claims"]
                                        if c["decision_support"] != "clear"]
                return _reply(start_response, "200 OK", result)
            if method == "GET" and len(parts) == 3 and parts[0] == "records" and parts[2] == "trail":
                record = store.get(parts[1])
                trail = {"record": record, "relationships": [], "decisions": []}
                trail["relationships"] = [r for r in store.list_records("relationships", current_only=False)
                                          if r["from_id"] == parts[1] or r["to_id"] == parts[1]]
                trail["decisions"] = [d for d in store.list_records("decisions", current_only=False)
                                      if d["subject_ref"] == parts[1]]
                return _reply(start_response, "200 OK", trail)
            if method == "GET" and parts == ["export", "claims"]:
                trip_id = parse_qs(parsed.query).get("trip_id", [None])[0]
                result = [claims.public(c) for c in claims.build_claims(store, trip_id, cfg)]
                return _reply(start_response, "200 OK", {"claims": result})
            return _reply(start_response, "404 Not Found", {"error": "not_found"})
        except (KeyError, ValueError, TypeError) as exc:
            return _reply(start_response, "400 Bad Request", {"error": str(exc)})
    return app
