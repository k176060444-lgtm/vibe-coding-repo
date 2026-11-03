"""CLI entry points: python -m blindreview worker|coordinate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .coordinator import Coordinator
from .worker import serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Persistent remote blind-review worker and polling coordinator")
    group = parser.add_subparsers(dest="command", required=True)
    worker = group.add_parser("worker", help="start one remote review worker")
    worker.add_argument("--config", required=True, type=Path)
    coordinator = group.add_parser("coordinate", help="coordinate 2-of-3 reviewers")
    coordinator.add_argument("--config", required=True, type=Path)
    coordinator.add_argument("--state-dir", required=True, type=Path)
    coordinator.add_argument("--resume", action="store_true")
    reconcile = group.add_parser("reconcile", help="retry cancellation after a network outage")
    reconcile.add_argument("--config", required=True, type=Path)
    reconcile.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    try:
        if args.command == "worker":
            serve(config)
            return 0
        runner = Coordinator(config, args.state_dir)
        if args.command == "reconcile":
            runner.initialize(resume=True)
            pending = runner.reconcile_cancellations()
            print(json.dumps({"pending_cancellations": pending}, ensure_ascii=False))
            return 3 if pending else 0
        runner.initialize(resume=args.resume)
        outcome = runner.run()
        print(json.dumps({"outcome": outcome, "summary": str(args.state_dir / 'summary.json')}, ensure_ascii=False))
        return 0 if outcome == "QUORUM_MET" else 2
    except KeyboardInterrupt:
        print("Interrupted: persisted state can be resumed using --resume", file=sys.stderr)
        return 130
    except (ValueError, OSError, KeyError) as exc:
        print(f"Configuration/runtime error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
