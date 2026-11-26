import argparse
import importlib.util
import itertools
import json
from pathlib import Path
from types import SimpleNamespace

parser = argparse.ArgumentParser()
parser.add_argument("root", type=Path)
parser.add_argument("reference", type=Path)
args = parser.parse_args()
root = args.root
spec = importlib.util.spec_from_file_location("paired", root / "src/curvine-tests/benchmark/worker-io-uring-paired.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)

dest = root / "final"
dest.mkdir(exist_ok=True)
arms = ["small", "old", "off"]
for arm in arms:
    (dest / arm).mkdir(exist_ok=True)
binaries = root / "final-bin"
cells = ["fuse-4-read-64", "client-128-read-64", "client-4-read-64", "client-128-write-1"]
orders = list(itertools.permutations(arms))
active = dest / "active.jsonl"
if (dest / "rows.jsonl").exists():
    raise SystemExit("final matrix is already complete")
with active.open("a") as output:
    previous = [json.loads(line) for line in active.read_text().splitlines()]
    done = {(r["pair"], r["cell"], r["arm"]) for r in previous}
    for group in range(6):
        for index, cell in enumerate(cells):
            order = orders[(group + index) % len(orders)]
            ports = paired.bench.allocate_ports()
            for arm in order:
                if (group + 1, cell, arm) in done:
                    continue
                server = args.reference if arm == "old" else binaries
                settings = SimpleNamespace(server=server / "curvine-server", cli=binaries / "curvine-cli",
                                           fuse=binaries / "curvine-fuse", seconds=20)
                row = paired.measure(settings, dest / arm, group + 1, arm != "off", cell, ports)
                row["arm"] = arm
                print(json.dumps(row), file=output, flush=True)
                print(group + 1, cell, arm, row["result"]["value"], flush=True)
assert len(active.read_text().splitlines()) == 72
active.rename(dest / "rows.jsonl")
