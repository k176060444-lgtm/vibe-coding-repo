"""P0.3 focused reliability regressions. All execution is on isolated fixtures."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from blindreview.common import ProtocolError, local_host_fingerprint
from blindreview.coordinator import Coordinator
from blindreview.http_client import ReviewClient, TransportError
from blindreview.worker import Worker
from test_pipeline import FakeClient, synthetic_host_fingerprint, make_repo


class CoordinatorReliability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 12000.0
        self.nodes = [dict(id=n, url="http://"+n+".example", physical_host_id="host-"+n,
                           host_fingerprint=synthetic_host_fingerprint(n),
                           token_env="TOKEN_"+n, harness="mock", model="test")
                      for n in ("A", "B", "C")]
        self.cfg = dict(task_id="T1", repository="fixture", commit_sha="a"*40,
                        contract_sha256="b"*64, nodes=self.nodes,
                        overall_deadline_seconds=3600, third_grace_seconds=600,
                        poll_interval_seconds=60)
        self.clients = {n: FakeClient(n, lambda: self.now) for n in ("A","B","C")}
        self.runner = None

    def coordinator(self, resume=False):
        c=Coordinator(self.cfg, Path(self.tmp.name), clock=lambda:self.now,
                      client_factory=lambda node:self.clients[node["id"]])
        c.initialize(resume=resume)
        self.runner=c
        return c

    def tearDown(self):
        if self.runner:
            self.runner.close()
        self.tmp.cleanup()

    def test_duplicate_fingerprint_declared_hosts_rejected(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["nodes"][1]["host_fingerprint"]=cfg["nodes"][0]["host_fingerprint"]
        with self.assertRaises(ValueError):
            Coordinator(cfg, Path(self.tmp.name), clock=lambda:self.now,client_factory=lambda node:self.clients[node["id"]])

    def test_unexpected_host_fingerprint_cannot_be_counted(self):
        c=self.coordinator()
        self.clients["A"].finish_at=self.now
        self.clients["B"].finish_at=self.now
        self.clients["C"].finish_at=self.now+9999
        original=self.clients["B"].status
        def spoofed(job):
            value=original(job)
            value["host_fingerprint"]="c"*64
            return value
        self.clients["B"].status=spoofed
        self.assertIsNone(c.step())
        self.assertEqual(c.state["accepted_nodes"],["A"])
        self.assertIn("identity",str(c.state["jobs"]["B"]["last_error"]).lower())

    def test_second_receipt_survives_state_crash_after_file_replace(self):
        c=self.coordinator()
        self.clients["A"].finish_at=self.now+60
        self.clients["B"].finish_at=self.now+60
        self.clients["C"].finish_at=self.now+9999
        c.step()  # all three tasks are running before the receipt crash
        self.now+=60
        original=c._save
        def crash_after_receipt():
            if (Path(self.tmp.name)/"receipts"/"B.json").is_file():
                raise SystemExit("Simulated crash before state commit")
            original()
        with patch.object(c,"_save",side_effect=crash_after_receipt):
            with self.assertRaises(SystemExit):
                c.step()
        self.assertTrue((Path(self.tmp.name)/"receipts"/"B.json").exists())
        c.close()
        self.now+=601
        resumed=self.coordinator(resume=True)
        self.assertEqual(resumed.state["quorum_at"],12060.0)
        self.assertEqual(resumed.step(),"QUORUM_MET")
        self.assertEqual(set(resumed.state["accepted_nodes"]),{"A","B"})
        self.assertEqual(self.clients["C"].cancel_count,1)

    def test_failure_quorum_cancels_outstanding_third(self):
        c=self.coordinator()
        self.clients["C"].finish_at=self.now+9999
        for n in ("A","B"):
            original=self.clients[n].status
            def failed(job,orig=original):
                value=orig(job)
                value["state"]="FAILED"
                return value
            self.clients[n].status=failed
        self.assertEqual(c.step(),"FAILED_INSUFFICIENT_REVIEWERS")
        self.assertEqual(self.clients["C"].cancel_count,1)
        self.assertTrue(c.state["jobs"]["C"]["cancel_requested"])

    def test_clock_rollback_does_not_extend_grace(self):
        c=self.coordinator()
        self.clients["A"].finish_at=self.now
        self.clients["B"].finish_at=self.now
        self.clients["C"].finish_at=self.now+9999
        self.assertIsNone(c.step())
        self.now-=10
        with self.assertRaises(ProtocolError):
            c.step()


class WorkerReliability(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        repo=root/"repo";repo.mkdir()
        self.sha=make_repo(repo)
        self.contract=root/"contract.md";self.contract.write_text("Review code only",encoding="utf8")
        self.cfg=dict(node_id="testnode",physical_host_id="HOST1",workdir=str(root/"work"),
                      contract_path=str(self.contract),repositories={"fixture":str(repo)},
                      harnesses={"mock":{"command":[sys.executable,"-c","pass"]}},
                      max_job_seconds=7,heartbeat_seconds=1)
        self.req=dict(job_id="j1",task_id="T1",repository="fixture",commit_sha=self.sha,
                      contract_sha256=hashlib.sha256(self.contract.read_bytes()).hexdigest(),
                      role="blind-review",harness="mock",model="test")
        self.workers=[]

    def tearDown(self):
        for w in self.workers:
            w.shutdown();w.store.close()
        self.tmp.cleanup()

    def test_host_fingerprint_is_os_derived_not_configurable(self):
        first=local_host_fingerprint()
        self.assertEqual(len(first),64)
        c=dict(self.cfg,host_fingerprint="a"*64)
        w=Worker(c);self.workers.append(w)
        self.assertEqual(w.host_fingerprint,first)

    def test_casefold_secret_always_removed_from_child_env(self):
        c=dict(self.cfg,token_env="BLIND_REVIEW_SECURE_TOKEN",
               env_allowlist=["blind_review_secure_token","BLIND_REVIEW_SECURE_TOKEN","PATH"])
        with patch.dict(os.environ,{"BLIND_REVIEW_SECURE_TOKEN":"fixture-token-for-test"},clear=False):
            w=Worker(c);self.workers.append(w)
            env=w._child_env()
            self.assertFalse(any(k.casefold()=="blind_review_secure_token" for k in env))

    @unittest.skipIf(os.name=="nt","POSIX process-group test; Windows uses Job Object")
    def test_parent_exit_cannot_leave_writable_descendant(self):
        marker=Path(self.tmp.name)/"late-marker.txt"
        child_script="import time;from pathlib import Path;time.sleep(0.8);Path("+repr(str(marker))+").write_text('late')"
        root_script="import sys,subprocess;subprocess.Popen([sys.executable,'-c',"+repr(child_script)+"])"
        c=copy.deepcopy(self.cfg)
        c["harnesses"]["mock"]["command"]=[sys.executable,"-c",root_script]
        w=Worker(c);self.workers.append(w)
        w.submit(self.req)
        stop=time.monotonic()+5
        while time.monotonic()<stop:
            row=w.store.get("j1")
            if row["state"] in ("FAILED","COMPLETED","INTERRUPTED","CANCELLED","TIMED_OUT"):
                break
            time.sleep(.02)
        self.assertNotEqual(row["state"],"RUNNING")
        time.sleep(1.0)
        self.assertFalse(marker.exists(),"descendant survived after root process completed")


class ClientReliability(unittest.TestCase):
    def test_header_drip_is_bounded_by_absolute_deadline(self):
        class SlowHead(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    self.wfile.write(b"HTTP/1.1 200 OK\r\n")
                    self.wfile.flush()
                    for _ in range(25):
                        self.wfile.write(b"X");self.wfile.flush()
                        time.sleep(.07)
                except OSError:
                    pass
            def log_message(self,*args): pass
        server=ThreadingHTTPServer(("127.0.0.1",0),SlowHead)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            start=time.monotonic()
            with self.assertRaises(TransportError):
                ReviewClient(f"http://127.0.0.1:{server.server_port}","local-test-token",timeout=.2).status("j1")
            self.assertLess(time.monotonic()-start,.85)
        finally:
            server.shutdown();server.server_close()


if __name__=="__main__":
    unittest.main()
