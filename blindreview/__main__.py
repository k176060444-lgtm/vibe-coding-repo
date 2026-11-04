"""P0 worker and coordinator CLI; machine-readable for a separate P1 orchestrator."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import ProtocolError, local_host_fingerprint
from .coordinator import Coordinator
from .worker import serve


def _load_config(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Durable cross-node blind-review executor (P0 only)")
    group = parser.add_subparsers(dest="command", required=True)
    group.add_parser("host-id", help="print local OS fingerprint for trusted enrollment")
    worker = group.add_parser("worker", help="start one remote review worker")
    worker.add_argument("--config", required=True, type=Path)
    for name, help_text in [
        ("coordinate", "coordinate until quorum or terminal failure"),
        ("init", "create durable coordinator job IDs without dispatching"),
        ("step", "execute one bounded round of submission/status/reports"),
        ("reconcile", "retry unconfirmed remote cancellations"),
        ("cancel", "persist cancellation and request remote stop"),
        ("collect", "validate and list locally accepted reports"),
    ]:
        cmd = group.add_parser(name, help=help_text)
        cmd.add_argument("--config", required=True, type=Path)
        cmd.add_argument("--state-dir", required=True, type=Path)
        if name == "coordinate":
            cmd.add_argument("--resume", action="store_true")
    status = group.add_parser("status", help="read only the current durable local state")
    status.add_argument("--state-dir", required=True, type=Path)
    args = parser.parse_args()

    try:
        if args.command == "host-id":
            print(json.dumps({"host_fingerprint": local_host_fingerprint()}))
            return 0
        if args.command == "status":
            state = json.loads((args.state_dir / "state.json").read_text(encoding="utf-8"))
            print(json.dumps({"run_id": state["run_id"], "result": state["result"],
                              "accepted_nodes": state["accepted_nodes"],
                              "jobs": {nid: {"job_id": j["request"]["job_id"], "state": j["state"],
                                             "valid": j["valid"], "cancel_requested": j["cancel_requested"]}
                                       for nid, j in state["jobs"].items()}},
                             ensure_ascii=False, sort_keys=True))
            return 0
        config = _load_config(args.config)
        if args.command == "worker":
            serve(config)
            return 0
        runner = Coordinator(config, args.state_dir)
        try:
            if args.command == "init":
                runner.initialize()
                print(json.dumps({"run_id": runner.state["run_id"], "state_dir": str(args.state_dir),
                                  "jobs": {nid: j["request"]["job_id"] for nid, j in runner.state["jobs"].items()}},
                                 ensure_ascii=False))
                return 0
            runner.initialize(resume=args.command != "coordinate" or args.resume)
            if args.command == "reconcile":
                pending = runner.reconcile_cancellations()
                print(json.dumps({"pending_cancellations": pending}, ensure_ascii=False))
                return 3 if pending else 0
            if args.command == "step":
                outcome = runner.step()
                print(json.dumps({"run_id": runner.state["run_id"], "result": outcome,
                                  "accepted_nodes": runner.state["accepted_nodes"],
                                  "pending_cancellations": [nid for nid, j in runner.state["jobs"].items()
                                                            if j["cancel_requested"] and j["state"] not in
                                                            ("COMPLETED","FAILED","TIMED_OUT","CANCELLED","INTERRUPTED")]},
                                 ensure_ascii=False))
                return 0 if outcome in (None, "QUORUM_MET") else 2
            if args.command == "collect":
                if runner.state["result"] != "QUORUM_MET":
                    raise ProtocolError("Cannot collect as successful quorum before QUORUM_MET")
                results = {nid: {"path": str(runner.state_dir / "reports" / (nid + ".json")),
                                 "report_sha256": runner.state["jobs"][nid]["report_sha256"],
                                 "host_fingerprint": runner.node_map[nid]["host_fingerprint"]}
                           for nid in runner.state["accepted_nodes"]}
                print(json.dumps({"run_id": runner.state["run_id"], "reports": results}, ensure_ascii=False))
                return 0
            if args.command == "cancel":
                if runner.state["result"] is None:
                    runner._finalize("CANCELLED")
                pending = runner.reconcile_cancellations()
                print(json.dumps({"result": runner.state["result"], "pending_cancellations": pending}, ensure_ascii=False))
                return 3 if pending else 0
            outcome = runner.run()
            print(json.dumps({"outcome": outcome, "summary": str(args.state_dir / "summary.json")}, ensure_ascii=False))
            return 0 if outcome == "QUORUM_MET" else 2
        finally:
            runner.close()
    except KeyboardInterrupt:
        print("Interrupted: use --resume or reconcile to inspect persisted jobs", file=sys.stderr)
        return 130
    except (ProtocolError, ValueError, OSError, KeyError) as exc:
        print(f"Configuration/runtime error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
