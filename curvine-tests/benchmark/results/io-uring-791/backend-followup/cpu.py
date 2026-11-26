import importlib.util, json, os, resource, sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
root, ref = map(Path, sys.argv[1:])
spec=importlib.util.spec_from_file_location("paired",root/"src/curvine-tests/benchmark/worker-io-uring-paired.py")
p=importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
original_mount=p.mounted
processes={}
@contextmanager
def mounted(*args):
    with original_mount(*args) as (mount, daemon):
        processes["fuse"]=daemon.pid
        yield mount, daemon
p.mounted=mounted
original_wait=p.bench.wait_cluster
def wait_cluster(*args):
    master,worker=original_wait(*args)
    processes.update(master=master.pid,worker=worker.pid)
    return master,worker
p.bench.wait_cluster=wait_cluster
original_cli=p.bench.run_cli
def sample():
    vals={}
    for name,pid in processes.items():
        cols=Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()
        vals[name]=(int(cols[11])+int(cols[12]))/os.sysconf("SC_CLK_TCK")
    cli=resource.getrusage(resource.RUSAGE_CHILDREN)
    vals["cli"]=cli.ru_stime+cli.ru_utime
    return vals
def run_cli(cmd,out,state,phase,timeout,report,worker=None):
    if phase!="measure":
        return original_cli(cmd,out,state,phase,timeout,report,worker)
    before=sample()
    result=original_cli(cmd,out,state,phase,timeout,report,worker)
    after=sample()
    (out/"cpu.json").write_text(json.dumps({k:round(after[k]-v,3) for k,v in before.items()}))
    return result
p.bench.run_cli=run_cli
dest=root/"component"
dest.mkdir(exist_ok=True)
args=SimpleNamespace(server=ref/"curvine-server",cli=ref/"curvine-cli",fuse=ref/"curvine-fuse",seconds=12)
with (dest/"rows.jsonl").open("w") as f:
    for cell in ["fuse-4-read-64","client-128-read-64"]:
        for enabled in (True,False):
            processes.clear()
            row=p.measure(args,dest,1,enabled,cell,p.bench.allocate_ports())
            row["process_cpu_seconds"]=json.loads((dest/f"1-{cell}-{int(enabled)}"/"cpu.json").read_text())
            print(json.dumps(row),file=f,flush=True)
