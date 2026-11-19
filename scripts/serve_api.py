#!/usr/bin/env python3
"""Standalone runner for the Member B Core Engine & Trust WSGI HTTP server."""
import argparse
import os
import sys
from wsgiref.simple_server import make_server

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from pratibimb import Store, cases, linking  # noqa: E402
from pratibimb.api import create_app  # noqa: E402
from pratibimb.config import load_config  # noqa: E402
from pratibimb.fixtures import load_into  # noqa: E402


def build_seeded_store(db_path=":memory:", seed=True):
    cfg = load_config()
    store = Store(db_path)
    existing = store.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    if seed and existing == 0:
        idx = load_into(store)
        for sc in idx.values():
            for it in sc["keys"].values():
                linking.link_interpretation(store, it["interp_id"], cfg)
        cases.reconcile(store, "trip_demo", cfg)
        cases.sync_cases(store, "trip_demo", cfg)
        store.add_join_code("trip_demo", "coordinator:demo", code="DEMO2026")
        store.add_trip("Bengaluru Fest Trip", "coordinator:demo", trip_id="trip_bengaluru_fest_01")
        store.add_join_code("trip_bengaluru_fest_01", "coordinator:demo", code="METRO2026")
    return store, cfg


def main():
    parser = argparse.ArgumentParser(description="Run the Pratibimb Member B Core Engine API server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=":memory:", help="SQLite DB path or :memory:")
    parser.add_argument("--no-seed", action="store_true", help="Start with an empty database")
    args = parser.parse_args()

    store, cfg = build_seeded_store(args.db, seed=not args.no_seed)
    print(f"Pratibimb Core API listening on http://{args.host}:{args.port} (db={args.db})", flush=True)
    try:
        make_server(args.host, args.port, create_app(store, cfg)).serve_forever()
    except KeyboardInterrupt:
        print("Server stopped.", flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
