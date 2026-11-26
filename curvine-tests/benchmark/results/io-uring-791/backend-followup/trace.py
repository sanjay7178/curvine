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
program = r"""
BEGIN { printf("READY\n"); }
tracepoint:io_uring:io_uring_submit_req
/pid == $1 && args.opcode == 23/ { @start[args.req] = nsecs; @writes = count(); }
tracepoint:io_uring:io_uring_queue_async_work
/@start[args.req]/ { @queued = count(); }
tracepoint:io_uring:io_uring_complete
/@start[args.req]/ {
    $us = (nsecs-@start[args.req])/1000; @kernel_us = hist($us); @mean_us = avg($us);
    @bytes = sum(args.res >= 0 ? args.res : 0);
    @complete = count(); delete(@start,args.req);
}
tracepoint:syscalls:sys_enter_newfstatat,tracepoint:syscalls:sys_enter_newfstat,tracepoint:syscalls:sys_enter_statx
/pid == $1/ { @stat_calls = count(); @stat_start[tid] = nsecs; }
tracepoint:syscalls:sys_exit_newfstatat,tracepoint:syscalls:sys_exit_newfstat,tracepoint:syscalls:sys_exit_statx
/@stat_start[tid]/ { @stat_ns = sum(nsecs-@stat_start[tid]); delete(@stat_start,tid); }
END { clear(@start); clear(@stat_start); }
"""
def traced(cmd,out,state,phase,timeout,report,worker=None):
    if phase != "measure":
        return original(cmd,out,state,phase,timeout,report,worker)
    script=root/"io.bt"
    script.write_text(program)
    log=root/"trace.log"
    with log.open("w") as stream:
        proc=subprocess.Popen(["sudo","-n","--","timeout","--signal=INT","35","stdbuf","-oL","bpftrace",str(script),str(worker.pid)],stdout=stream,stderr=subprocess.STDOUT)
        try:
            for i in range(100):
                if "\nREADY\n" in log.read_text():
                    break
                if proc.poll() is not None:
                    raise RuntimeError(log.read_text())
                time.sleep(.1)
            else:
                raise RuntimeError("trace did not attach")
            return original(cmd,out,state,phase,timeout,report,worker)
        finally:
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=40)
p.bench.run_cli=traced
out=root/"trace"
out.mkdir(exist_ok=True)
args=SimpleNamespace(server=ref/"curvine-server",cli=ref/"curvine-cli",fuse=ref/"curvine-fuse",seconds=20)
row=p.measure(args,out,1,True,"client-128-write-1",p.bench.allocate_ports())
(out/"row.json").write_text(json.dumps(row,indent=2))
