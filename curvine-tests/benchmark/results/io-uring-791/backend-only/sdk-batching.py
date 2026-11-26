"""Compare batch sizes one and four with a single standalone SDK and LocalFile."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("paired", Path(__file__).resolve().parents[3] / "worker-io-uring-paired.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
bench = paired.bench
bins, cli, output = [Path(arg).resolve() for arg in sys.argv[1:]]
output.mkdir()
args = SimpleNamespace(server=bins/"curvine-server", cli=cli, fuse=bins/"curvine-fuse", seconds=20)
original = bench.run_cli


def run_client(cmd, out, state, phase, *other):
    config = out / "client.toml"
    if not config.exists():
        raw = (out / "cluster.toml").read_text().replace("enable_io_uring = false\n", "")
        config.write_text(raw.replace("[client]", f"[client]\nwrite_batch_chunks = {depth}"))
    cmd = list(cmd)
    cmd[cmd.index("--conf") + 1] = str(config)
    return original(cmd, out, state, phase, *other)


bench.run_cli = run_client
with (output / "runs.jsonl").open("x") as rows:
    for pair in range(1, 7):
        for threads in (1, 16):
            ports = bench.allocate_ports()
            for depth in ((1, 4) if (pair + threads) % 2 else (4, 1)):
                out = output / f"{pair}-{threads}-{depth}"
                out.mkdir()
                row = paired.measure(args, out, pair, False, f"client-128-write-{threads}", ports)
                print(json.dumps(dict(depth=depth, **row)), file=rows, flush=True)
