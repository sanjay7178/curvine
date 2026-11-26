"""Measure a verified 4 KiB read at a randomized open offset in each file."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import sys
import tempfile
import time
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("paired", Path(__file__).resolve().parents[3] / "worker-io-uring-paired.py")
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
bench = paired.bench
bins, dest = [Path(arg).resolve() for arg in sys.argv[1:]]
dest.mkdir()
opts = SimpleNamespace(fuse=bins / "curvine-fuse")
count = 256
size = 256 * 1024
page = 4096
data = [random.Random(i + 791).randbytes(size) for i in range(count)]
digest = hashlib.sha256(b"".join(data)).hexdigest()


def trial(out, ports, pair, enabled):
    out.mkdir()
    conf = out / "cluster.toml"
    text = bench.cluster_toml(ports, enabled).replace('read_chunk_size = "1MB"', 'read_chunk_size = "4KB"')
    conf.write_text(text.replace("[client]", "[client]\nread_pipeline_depth = 1") + paired.MOUNT_SETTINGS)
    with ExitStack() as stack:
        state = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=out)))
        master, worker = bench.wait_cluster(stack, bins / "curvine-server", conf, state, out, ports, 45)
        mount, _ = stack.enter_context(paired.mounted(opts, state, out, conf, master, worker, {}))
        paths = [mount / f"page-{i}" for i in range(count)]
        with ThreadPoolExecutor(16) as pool:
            list(pool.map(lambda item: paths[item].write_bytes(data[item]), range(count)))
            blocks = [p for p in (state / "blocks").glob("**/active/b*/b*/*")
                      if p.is_file() and p.stat().st_size == size]
            if len(blocks) != count:
                raise ValueError(f"found {len(blocks)} finalized blocks; expected {count}")
            rng = random.Random(pair)
            order = list(range(count))
            rng.shuffle(order)
            offsets = [page * rng.randrange(size // page) for _ in range(count)]

            def read(i):
                offset = offsets[i]
                start = time.perf_counter_ns()
                with paths[i].open("rb", buffering=0) as f:
                    value = os.pread(f.fileno(), page, offset)
                latency = time.perf_counter_ns() - start
                if value != data[i][offset:offset + page]:
                    raise ValueError("random page differs from input")
                return latency

            for cache in ("guest-cold-advised", "warm"):
                for block in blocks:
                    with block.open("rb") as f:
                        if cache == "guest-cold-advised":
                            os.fsync(f.fileno())
                            os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
                        else:
                            f.read()
                before = bench.scrape(out, ports, cache + "-before")
                device = paired.device_read_bytes(worker)
                u0, s0, _ = bench.cpu_sample(out, worker, cache + "-cpu0")
                start = time.perf_counter_ns()
                samples = sorted(pool.map(read, order))
                elapsed = time.perf_counter_ns() - start
                u1, s1, _ = bench.cpu_sample(out, worker, cache + "-cpu1")
                device = paired.device_read_bytes(worker) - device
                after = bench.scrape(out, ports, cache + "-after")
                sizes = {k: paired.counter(after, k) - paired.counter(before, k)
                         for k in ("read_bytes", "read_count", "worker_io_uring_read_bytes")}
                if sizes["read_count"] < count or sizes["read_bytes"] != page * sizes["read_count"]:
                    raise ValueError(f"unexpected number of worker reads: {sizes}")
                if sizes["worker_io_uring_read_bytes"] != enabled * sizes["read_bytes"]:
                    raise ValueError(f"unexpected backend routing: {sizes}")
                yield dict(pair=pair, enabled=enabled, cache=cache, **sizes, input_sha256=digest,
                           application_bytes=count * page, verified_pages=count, wall_ns=elapsed,
                           iops=count * 1e9 / elapsed, p95_us=samples[math.ceil(.95*count)-1]/1000,
                           p99_us=samples[math.ceil(.99*count)-1]/1000,
                           cpu_seconds=(u1+s1-u0-s0)/os.sysconf("SC_CLK_TCK"),
                           process_storage_read_bytes=device)


with (dest / "runs.jsonl").open("x") as rows:
    for pair in range(1, 7):
        ports = bench.allocate_ports()
        for enabled in ((False, True) if pair % 2 else (True, False)):
            for row in trial(dest / f"{pair}-{int(enabled)}", ports, pair, enabled):
                print(json.dumps(row), file=rows, flush=True)
                print(pair, enabled, row["cache"], round(row["iops"]), flush=True)
