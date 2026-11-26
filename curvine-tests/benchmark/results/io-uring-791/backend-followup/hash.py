import hashlib
import importlib.util
import json
import random
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("paired", root / "src/curvine-tests/benchmark/worker-io-uring-paired.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
bench = paired.bench
bin_dir = root / "final-bin"
settings = SimpleNamespace(fuse=bin_dir / "curvine-fuse")
results = []
for enabled in (False, True):
    out = root / "hashes" / str(int(enabled))
    out.mkdir(parents=True, exist_ok=True)
    ports = bench.allocate_ports()
    conf = out / "cluster.toml"
    config = bench.cluster_toml(ports, enabled).replace('read_chunk_size = "1MB"', 'read_chunk_size = "4KB"')
    conf.write_text(config.replace("[client]", "[client]\nread_pipeline_depth = 4") + paired.MOUNT_SETTINGS)
    with ExitStack() as stack:
        state = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=out)))
        master, worker = bench.wait_cluster(stack, bin_dir / "curvine-server", conf, state, out, ports, 45)
        record = {"enabled": enabled}
        cli = [str(bin_dir / "curvine-cli"), "--conf", str(conf), "--master-addrs", f"{bench.HOST}:{ports.master_rpc}", "fs"]
        def run(*args):
            subprocess.run(cli + list(map(str, args)), cwd=state, env=bench.child_env(state),
                           check=True, capture_output=True, timeout=45)
        mount, daemon = stack.enter_context(paired.mounted(settings, state, out, conf, master, worker, record))
        source = state / "input"
        data = random.Random(2497).randbytes(4 * 2**20 + 257)
        source.write_bytes(data)
        # Metrics with per-directory labels appear on the first data operation.
        # Exercise both directions before taking the measured counter baseline.
        prime = state / "prime"
        prime.write_bytes(b"prime")
        run("put", prime, "cv://default/prime")
        run("get", "cv://default/prime", state / "prime-read")
        before = bench.scrape(out, ports, "before")
        run("put", source, "cv://default/verify")
        destination = state / "output"
        run("get", "cv://default/verify", destination)
        assert destination.read_bytes() == data
        assert (mount / "verify").read_bytes() == data
        record["sdk_to_fuse_sha256"] = hashlib.sha256(data).hexdigest()
        second = random.Random(791).randbytes(3 * 2**20 + 123)
        (mount / "from-mount").write_bytes(second)
        destination.unlink()
        run("get", "cv://default/from-mount", destination)
        assert destination.read_bytes() == second
        record["fuse_to_sdk_sha256"] = hashlib.sha256(second).hexdigest()
        after = bench.scrape(out, ports, "after")
        for direction, expected in (("read", len(data)*2 + len(second)), ("write", len(data) + len(second))):
            delta = paired.counter(after, direction+"_bytes") - paired.counter(before, direction+"_bytes")
            ring = bench.ring_deltas(before, after)[direction]["delta_bytes"]
            assert delta == expected and ring == int(enabled)*expected, (direction, delta, ring, expected)
            record[direction+"_bytes"] = delta
            record[direction+"_ring_bytes"] = ring
        results.append(record)
(root/"hashes/results.json").write_text(json.dumps(results,indent=2)+"\n")
