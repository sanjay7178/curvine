import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace
root, ref = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("paired",root/"src/curvine-tests/benchmark/worker-io-uring-paired.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
original = p.bench.run_cli
def traced(cmd,out,state,phase,timeout,report,worker=None):
    if phase != "measure":
        return original(cmd,out,state,phase,timeout,report,worker)
    with (root/"perf-record.log").open("w") as stream:
        proc=subprocess.Popen(["sudo","-n","--","perf","record","-q","-F","149","-e","cpu-clock",
            "-p",str(worker.pid),"-o",str(root/"worker.perf"),"--","sleep","24"],stdout=stream,stderr=subprocess.STDOUT)
        try:
            time.sleep(0.5)
            if proc.poll() is not None:
                raise RuntimeError("perf could not attach")
            return original(cmd,out,state,phase,timeout,report,worker)
        finally:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=30)
p.bench.run_cli=traced
out=root/"perf"
out.mkdir(exist_ok=True)
args=SimpleNamespace(server=ref/"curvine-server",cli=ref/"curvine-cli",fuse=ref/"curvine-fuse",seconds=9)
row=p.measure(args,out,1,True,"client-128-read-64",p.bench.allocate_ports())
(out/"row.json").write_text(json.dumps(row,indent=2))
