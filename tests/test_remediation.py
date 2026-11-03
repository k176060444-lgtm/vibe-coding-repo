"""P0/P1 adversarial regression tests. No real model or production host access."""
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

from blindreview.common import ProtocolError, bind_worker_report, report_bytes, validate_report
from blindreview.coordinator import Coordinator
from blindreview.http_client import ReviewClient, TransportError
from blindreview.store import JobStore
from blindreview.worker import Worker, ReviewHandler
from test_pipeline import FakeClient, make_repo

ROOT = Path(__file__).resolve().parents[1]

class Bindings(unittest.TestCase):
    def setUp(self):
        self.req = dict(job_id="j1", task_id="T1", repository="fixture", commit_sha="a" * 40,
                        role="blind-review", harness="fixture", model="test", contract_sha256="b" * 64)
        self.base = dict(job_id="j1", commit_sha="a" * 40, role="blind-review",
                         verdict="APPROVE", summary="Mock only", findings=[])

    def test_worker_adds_trusted_context_to_report(self):
        r = bind_worker_report(self.base, self.req, "nodeA", "physicalA")
        self.assertEqual(r["contract_sha256"], self.req["contract_sha256"])
        validate_report(r, self.req, "nodeA", "physicalA")

    def test_conflicting_task_rejected(self):
        with self.assertRaises(ProtocolError):
            bind_worker_report({**self.base, "task_id": "OTHER"}, self.req, "nodeA", "physicalA")

    def test_conflicting_contract_rejected(self):
        with self.assertRaises(ProtocolError):
            bind_worker_report({**self.base, "contract_sha256": "f"*64}, self.req, "nodeA", "physicalA")

    def test_missing_context_rejected_at_coordinator(self):
        with self.assertRaises(ProtocolError):
            validate_report(self.base, self.req, "nodeA", "physicalA")

    def test_bogus_verdict_type_normalized(self):
        with self.assertRaises(ProtocolError):
            bind_worker_report({**self.base, "verdict": []}, self.req, "nodeA", "physicalA")

    def test_bad_evidence_location_rejected(self):
        with self.assertRaises(ProtocolError):
            bind_worker_report({**self.base, "findings": [dict(severity="IMPORTANT", location="bogus", description="x")]},
                               self.req, "nodeA", "physicalA")


class CoordinatorRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 10000.0
        self.clients = {}
        self.nodes = [dict(id=n, physical_host_id="host-"+n, url=f"http://{n}.example",
                           token_env=f"TOKEN_{n}", harness="fixture", model="test") for n in ("A","B","C")]
        self.cfg = dict(task_id="TASK", repository="fixture", commit_sha="a"*40,
                        contract_sha256="b"*64, nodes=self.nodes, third_grace_seconds=600,
                        overall_deadline_seconds=3600, poll_interval_seconds=60)
        self.coord = None

    def client(self, node):
        c = FakeClient(node["id"], lambda: self.now)
        # FakeClient's physical_host_id is host-<node_id>
        self.clients[node["id"]] = c
        return c

    def create(self, resume=False):
        c = Coordinator(self.cfg, Path(self.tmp.name), clock=lambda: self.now,
                        client_factory=lambda n: self.clients[n["id"]] if resume else self.client(n))
        c.initialize(resume=resume)
        self.coord = c
        return c

    def tearDown(self):
        if self.coord:
            self.coord.close()
        self.tmp.cleanup()

    def test_duplicate_physical_host_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["nodes"][1]["physical_host_id"] = cfg["nodes"][0]["physical_host_id"]
        with self.assertRaises(ValueError):
            Coordinator(cfg, Path(self.tmp.name))

    def test_duplicate_token_env_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["nodes"][1]["token_env"] = cfg["nodes"][0]["token_env"]
        with self.assertRaises(ValueError):
            Coordinator(cfg, Path(self.tmp.name))

    def test_grace_over_600_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["third_grace_seconds"] = 601
        with self.assertRaises(ValueError):
            Coordinator(cfg, Path(self.tmp.name))

    def test_lock_prevents_two_coordinators(self):
        c = self.create()
        second = Coordinator(self.cfg, Path(self.tmp.name), clock=lambda: self.now,
                             client_factory=lambda n:self.clients[n["id"]])
        with self.assertRaises(ValueError):
            second.initialize(resume=True)
        c.close()
        second.initialize(resume=True)
        second.close()

    def test_report_hash_matches_file_bytes(self):
        c = self.create()
        self.clients["A"].finish_at = self.now
        self.clients["B"].finish_at = self.now
        self.clients["C"].finish_at = self.now + 900
        c.step()
        self.assertEqual(c.state["result"], None)
        for n in ("A", "B"):
            p = Path(self.tmp.name)/"reports"/f"{n}.json"
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), c.state["jobs"][n]["report_sha256"])

    def test_resume_rejects_modified_report(self):
        c = self.create()
        self.clients["A"].finish_at = self.now
        self.clients["B"].finish_at = self.now
        self.clients["C"].finish_at = self.now + 900
        c.step();c.close()
        (Path(self.tmp.name)/"reports"/"A.json").write_bytes(b"{}")
        with self.assertRaises(ProtocolError):
            self.create(resume=True)

    def test_crash_second_report_quorum_recovers(self):
        c = self.create()
        self.clients["A"].finish_at = self.now
        self.clients["B"].finish_at = self.now
        self.clients["C"].finish_at = self.now + 900
        c.step()
        q = c.state["quorum_at"]
        self.assertEqual(q, self.now)
        c.close()
        self.now += 601
        second = self.create(resume=True)
        self.assertEqual(second.step(), "QUORUM_MET")
        self.assertEqual(second.state["quorum_at"], q)

    def test_recovery_repairs_missing_quorum_stamp(self):
        c = self.create()
        self.clients["A"].finish_at = self.now
        self.clients["B"].finish_at = self.now
        self.clients["C"].finish_at = self.now + 900
        c.step();q = c.state["quorum_at"]
        state = c.state; state["quorum_at"] = None
        c._save();c.close()
        self.now += 2401
        second = self.create(resume=True)
        self.assertEqual(second.state["quorum_at"], q)
        self.assertEqual(second.step(), "QUORUM_MET")

    def test_resume_restores_lost_summary(self):
        c = self.create()
        for x in self.clients.values():
            x.finish_at = self.now
        self.assertEqual(c.step(), "QUORUM_MET")
        c.close()
        (Path(self.tmp.name)/"summary.json").unlink()
        self.create(resume=True)
        self.assertTrue((Path(self.tmp.name)/"summary.json").is_file())

    def test_completed_report_fetch_retry(self):
        c = self.create()
        for x in self.clients.values():
            x.finish_at = self.now
        real = self.clients["B"].report
        once = [True]
        def flaky(job):
            if once[0]:
                once[0] = False
                raise TransportError("synthetic network failure")
            return real(job)
        self.clients["B"].report = flaky
        self.assertIsNone(c.step())
        self.assertNotEqual(c.state["result"], "FAILED_INSUFFICIENT_REVIEWERS")
        self.now += 60
        self.assertEqual(c.step(), "QUORUM_MET")


class WorkerRegression(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        repo=root/"git";repo.mkdir()
        self.sha = make_repo(repo)
        self.contract=root/"contract.md"; self.contract.write_text("Original approved contract",encoding="utf-8")
        self.cfg = dict(node_id="node-1", physical_host_id="host-1", workdir=str(root/"work"),
                        contract_path=str(self.contract), repositories={"fixture":str(repo)},
                        harnesses={"mock":dict(command=[sys.executable,str(ROOT/"tests"/"mock_reviewer.py"),
                                                         "{report_path}","{job_id}","{commit_sha}","{workspace}"])},
                        heartbeat_seconds=1,max_job_seconds=6,clone_timeout_seconds=12,max_concurrent=1)
        self.req = dict(job_id="j1",task_id="T1",repository="fixture",commit_sha=self.sha,role="blind-review",
                        harness="mock",model="test",contract_sha256=hashlib.sha256(self.contract.read_bytes()).hexdigest())
        self.workers=[]

    def worker(self,cfg=None):
        w=Worker(cfg or self.cfg);self.workers.append(w);return w

    def wait(self,w,jid="j1"):
        t=time.monotonic()+10
        while time.monotonic()<t:
            row=w.store.get(jid)
            if row["state"] in ("COMPLETED","FAILED","TIMED_OUT","CANCELLED","INTERRUPTED"):
                return row
            time.sleep(.03)
        self.fail("worker timeout")

    def tearDown(self):
        for w in self.workers:
            w.shutdown();w.store.close()
        self.tmp.cleanup()

    def test_contract_changes_on_queue_recovery_fail_closed(self):
        w=self.worker()
        with patch.object(w,"schedule",return_value=None):
            w.submit(self.req)
        self.assertEqual(w.store.get("j1")["state"],"QUEUED")
        w.shutdown();w.store.close();self.workers.remove(w)
        self.contract.write_text("Changed contract!",encoding="utf-8")
        resumed=self.worker();resumed.start_recovered()
        self.assertEqual(self.wait(resumed)["state"],"FAILED")

    def test_bounded_queue_no_per_job_threads(self):
        cfg=dict(self.cfg,max_queued=2)
        w=self.worker(cfg)
        blocker=threading.Event()
        original=w._run
        def blocked(jid):
            blocker.wait(3)
            return original(jid)
        with patch.object(w,"_run",side_effect=blocked):
            for i in range(3):
                w.submit({**self.req,"job_id":f"q{i}"})
            with self.assertRaises(ProtocolError):
                w.submit({**self.req,"job_id":"q3"})
            blocker.set()

    def test_worker_directory_exclusive(self):
        w=self.worker()
        with self.assertRaises(ValueError):
            Worker(self.cfg)
        w.shutdown()
        replacement=self.worker()
        self.assertIsNotNone(replacement.store)

    def test_hard_deadline_even_when_stdin_not_read(self):
        cfg=copy.deepcopy(self.cfg)
        self.contract.write_text("X"*180000,encoding="utf-8")
        self.req["contract_sha256"]=hashlib.sha256(self.contract.read_bytes()).hexdigest()
        cfg["max_job_seconds"]=1
        cfg["harnesses"]["mock"]=dict(command=[sys.executable,"-c","import time;time.sleep(10)"],
                                          stdin_prompt=True)
        w=self.worker(cfg)
        start=time.monotonic()
        w.submit(self.req)
        row=self.wait(w)
        self.assertEqual(row["state"],"TIMED_OUT",row["error"])
        self.assertLess(time.monotonic()-start,4.0)

    def test_monitoring_error_cleans_up_subprocess(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["harnesses"]["mock"]=dict(command=[sys.executable,"-c","import time;time.sleep(8)"])
        w=self.worker(cfg)
        processes=[]
        original=subprocess.Popen
        def tracked(*args, **kwargs):
            proc=original(*args, **kwargs)
            command=args[0] if args else kwargs.get("args",[])
            if isinstance(command,list) and len(command)>2 and command[1]=="-c":
                processes.append(proc)
            return proc
        with patch("blindreview.worker.subprocess.Popen",side_effect=tracked), \
             patch.object(w.store,"heartbeat",side_effect=OSError("synthetic heartbeat failure")):
            w.submit(self.req)
            result=self.wait(w)
        self.assertEqual(result["state"],"FAILED")
        self.assertTrue(processes)
        self.assertIsNotNone(processes[0].poll(),"failed child must be terminated")
        self.assertNotIn("j1",w._running)

    def test_local_clone_not_hardlinked_to_source(self):
        w=self.worker()
        w.submit(self.req)
        self.assertEqual(self.wait(w)["state"],"COMPLETED")
        src=Path(self.cfg["repositories"]["fixture"])/".git"/"objects"
        dst=Path(self.cfg["workdir"])/"jobs"/"j1"/"source"/".git"/"objects"
        shared=[]
        for a in src.rglob("*"):
            b=dst/a.relative_to(src)
            if a.is_file() and b.is_file() and a.stat().st_dev==b.stat().st_dev and a.stat().st_ino==b.stat().st_ino:
                shared.append(str(a))
        self.assertFalse(shared, shared)

    def test_report_binding_present_and_same_binary_hash(self):
        w=self.worker();w.submit(self.req)
        self.assertEqual(self.wait(w)["state"],"COMPLETED")
        p=Path(self.cfg["workdir"])/"jobs"/"j1"/"report.json"
        r=json.loads(p.read_bytes())
        self.assertEqual(r["contract_sha256"],self.req["contract_sha256"])
        self.assertEqual(r["physical_host_id"],"host-1")
        self.assertEqual(p.read_bytes(),report_bytes(r))

    def test_service_secret_not_inherited_by_harness(self):
        cfg=copy.deepcopy(self.cfg)
        cfg["token_env"]="SUPER_SECRET_WORKER_TOKEN"
        cfg["harnesses"]["mock"]["command"]=[sys.executable,"-c",
            "import os;from pathlib import Path;Path('secret-present').write_text(str('SUPER_SECRET_WORKER_TOKEN' in os.environ))"]
        old=os.environ.get("SUPER_SECRET_WORKER_TOKEN")
        os.environ["SUPER_SECRET_WORKER_TOKEN"]="fake-secret-for-test"
        try:
            w=self.worker(cfg);w.submit(self.req)
            self.assertEqual(self.wait(w)["state"],"FAILED")
            file=Path(cfg["workdir"])/"jobs"/"j1"/"source"/"secret-present"
            self.assertEqual(file.read_text(),"False")
        finally:
            if old is None:os.environ.pop("SUPER_SECRET_WORKER_TOKEN",None)
            else:os.environ["SUPER_SECRET_WORKER_TOKEN"]=old


class HTTPRegression(unittest.TestCase):
    def test_bearer_never_redirects_to_other_origin(self):
        captured=[]
        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                captured.append(self.headers.get("Authorization"));self.send_response(200)
                self.end_headers();self.wfile.write(b'{}')
            def log_message(self,*a): pass
        dest=ThreadingHTTPServer(("127.0.0.1",0),Destination)
        threading.Thread(target=dest.serve_forever,daemon=True).start()
        class Source(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302);self.send_header("Location",f"http://127.0.0.1:{dest.server_port}/steal")
                self.end_headers()
            def log_message(self,*a):pass
        src=ThreadingHTTPServer(("127.0.0.1",0),Source)
        threading.Thread(target=src.serve_forever,daemon=True).start()
        try:
            with self.assertRaises(TransportError):
                ReviewClient(f"http://127.0.0.1:{src.server_port}","synthetic-secret",timeout=1).status("j1")
            self.assertEqual(captured,[])
        finally:
            src.shutdown();src.server_close();dest.shutdown();dest.server_close()

    def test_slow_drip_cannot_extend_entire_response(self):
        class Slow(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.end_headers()
                for _ in range(12):
                    try:self.wfile.write(b" ");self.wfile.flush()
                    except (BrokenPipeError,ConnectionResetError):break
                    time.sleep(.07)
                try:self.wfile.write(b"{}")
                except (BrokenPipeError,ConnectionResetError):pass
            def log_message(self,*a):pass
        srv=ThreadingHTTPServer(("127.0.0.1",0),Slow)
        threading.Thread(target=srv.serve_forever,daemon=True).start()
        try:
            started=time.monotonic()
            with self.assertRaises(TransportError):
                ReviewClient(f"http://127.0.0.1:{srv.server_port}","token",timeout=.2).status("j1")
            self.assertLess(time.monotonic()-started,.7)
        finally:
            srv.shutdown();srv.server_close()

class EndToEndWire(unittest.TestCase):
    """Coordinator -> two HTTP Workers -> local Git -> mock harness -> reports."""
    def test_two_real_http_workers_quorum(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            repo=root/"repo";repo.mkdir()
            sha=make_repo(repo)
            contract=root/"contract.md";contract.write_text("Review code without writes",encoding="utf-8")
            contract_sha=hashlib.sha256(contract.read_bytes()).hexdigest()
            nodes, workers, servers, environments=[],[],[],{}
            try:
                for name in ("A","B"):
                    worker=Worker(dict(node_id=name,physical_host_id="physical-"+name,
                        workdir=str(root/("work-"+name)),contract_path=str(contract),
                        repositories={"fixture":str(repo)},heartbeat_seconds=1,max_job_seconds=12,
                        harnesses={"fixture":dict(command=[sys.executable,
                            str(ROOT/"tests"/"mock_reviewer.py"),
                            "{report_path}","{job_id}","{commit_sha}","{workspace}"])}))
                    workers.append(worker)
                    token="fixture-secret-token-"+name+"-aaaaaaaaaaaa"
                    handler=type("Handler"+name,(ReviewHandler,),{"worker":worker,"token":token})
                    server=ThreadingHTTPServer(("127.0.0.1",0),handler)
                    servers.append(server)
                    threading.Thread(target=server.serve_forever,daemon=True).start()
                    env="TEST_NODE_TOKEN_"+name
                    environments[env]=os.environ.get(env)
                    os.environ[env]=token
                    nodes.append(dict(id=name,physical_host_id="physical-"+name,
                        url=f"http://127.0.0.1:{server.server_port}",token_env=env,
                        harness="fixture",model="fixture-model"))
                cfg=dict(task_id="T1",repository="fixture",commit_sha=sha,contract_sha256=contract_sha,
                         nodes=nodes,request_timeout_seconds=3,poll_interval_seconds=1,
                         third_grace_seconds=0,overall_deadline_seconds=20)
                c=Coordinator(cfg,root/"coordinator")
                try:
                    c.initialize()
                    finish=time.monotonic()+15
                    while time.monotonic()<finish:
                        result=c.step()
                        if result is not None:
                            break
                        time.sleep(.1)
                    self.assertEqual(result,"QUORUM_MET",c.state)
                    self.assertEqual(len(c.state["accepted_nodes"]),2)
                    self.assertEqual({json.loads((root/"coordinator"/"reports"/(n+".json")).read_bytes())["physical_host_id"] for n in ("A","B")},
                                     {"physical-A","physical-B"})
                    for node in nodes:
                        path=root/"coordinator"/"reports"/(node["id"]+".json")
                        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                         c.state["jobs"][node["id"]]["report_sha256"])
                finally:
                    c.close()
            finally:
                for server in servers:
                    server.shutdown();server.server_close()
                for worker in workers:
                    worker.shutdown();worker.store.close()
                for env,original in environments.items():
                    if original is None:os.environ.pop(env,None)
                    else:os.environ[env]=original


if __name__ == "__main__": unittest.main()
