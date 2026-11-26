"""Replay the separate FUSE policy test against the local-file worker."""
from contextlib import contextmanager, ExitStack
from concurrent.futures import ThreadPoolExecutor
import math
import time
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import tempfile
from types import SimpleNamespace

path = Path(__file__).resolve().parents[3] / "worker-io-uring-paired.py"
spec = importlib.util.spec_from_file_location("paired", path)
paired = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paired)
bench = paired.bench
server, cli, fuse, output = map(lambda name: Path(name).resolve(), sys.argv[1:5])
output.mkdir()
args = SimpleNamespace(server=server, cli=cli, fuse=fuse, seconds=10)
mount_original = paired.mounted


@contextmanager
def policy_mount(args, state, out, conf, master, worker, record):
    daemon_conf = out / "fuse.toml"
    config = conf.read_text().replace("enable_io_uring = false\n", "").replace("enable_io_uring = true\n", "")
    if enabled:
        config = config.replace("[fuse]", "[fuse]\nlimit_prefetch_on_seek = true")
    daemon_conf.write_text(config)
    with mount_original(args, state, out, daemon_conf, master, worker, record) as mount:
        yield mount


def check_seeks(folder, ports):
    folder.mkdir()
    conf = folder / "cluster.toml"
    text = bench.cluster_toml(ports, False).replace('read_chunk_size = "1MB"', 'read_chunk_size = "4KB"')
    conf.write_text(text.replace("[client]", "[client]\nread_pipeline_depth = 4") + paired.MOUNT_SETTINGS)
    with ExitStack() as stack:
        state = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=folder)))
        master, worker = bench.wait_cluster(stack, server, conf, state, folder, ports, 45)
        mount, _ = stack.enter_context(policy_mount(args, state, folder, conf, master, worker, {}))
        payload = random.Random(791).randbytes(1 << 20)
        file = mount / "verify"
        file.write_bytes(payload)
        before = bench.scrape(folder, ports, "before")
        pages = random.Random(791).sample(range(250), 128)
        with file.open("rb", buffering=0) as stream:
            for page in pages:
                # Follow each seek with contiguous requests to restore the streaming limit.
                for next_page in range(page, page + 3):
                    offset = next_page * 4096
                    if os.pread(stream.fileno(), 4096, offset) != payload[offset:offset + 4096]:
                        raise ValueError("incorrect bytes after seek or contiguous read")
        after = bench.scrape(folder, ports, "after")
        return {key: paired.counter(after, key) - paired.counter(before, key)
                for key in ("read_bytes", "read_count", "worker_io_uring_read_bytes")}


def repeated_seeks(out, ports, pair):
    out.mkdir()
    conf = out / "cluster.toml"
    text = bench.cluster_toml(ports, False).replace('read_chunk_size = "1MB"', 'read_chunk_size = "4KB"')
    conf.write_text(text.replace("[client]", "[client]\nread_pipeline_depth = 4") + paired.MOUNT_SETTINGS)
    with ExitStack() as stack:
        state = Path(stack.enter_context(tempfile.TemporaryDirectory(dir=out)))
        master, worker = bench.wait_cluster(stack, server, conf, state, out, ports, 45)
        mount, _ = stack.enter_context(policy_mount(args, state, out, conf, master, worker, {}))
        files = [mount / f"random-{i}" for i in range(64)]
        payload = [random.Random(7133+i).randbytes(1 << 20) for i in range(64)]
        pages = [random.Random(787+i).sample(range(256),128) for i in range(64)]
        for file, data in zip(files,payload):
            file.write_bytes(data)

        def reader(lane):
            times = []
            for idx in range(lane,64,16):
                with files[idx].open("rb",buffering=0) as stream:
                    for page in pages[idx]:
                        offset = page * 4096
                        started = time.perf_counter_ns()
                        data = os.pread(stream.fileno(),4096,offset)
                        times.append(time.perf_counter_ns()-started)
                        if data != payload[idx][offset:offset+4096]:
                            raise ValueError("random read mismatch")
            return times

        with ThreadPoolExecutor(16) as pool:
            before = bench.scrape(out,ports,"before")
            u0,s0,_ = bench.cpu_sample(out,worker,"start")
            start = time.perf_counter_ns()
            samples = sorted(t for lane in pool.map(reader,range(16)) for t in lane)
            elapsed = time.perf_counter_ns()-start
            u1,s1,_ = bench.cpu_sample(out,worker,"end")
            after = bench.scrape(out,ports,"after")
        counts = {k:paired.counter(after,k)-paired.counter(before,k)
                  for k in ("read_count","read_bytes","worker_io_uring_read_bytes")}
        if len(samples)!=8192 or counts["worker_io_uring_read_bytes"]!=0 or counts["read_bytes"]!=4096*counts["read_count"]:
            raise RuntimeError("unexpected page or worker byte counters")
        return dict(pair=pair,policy=enabled,verified_pages=len(samples),application_bytes=4096*len(samples),
                    iops=len(samples)*1e9/elapsed,p95_us=samples[math.ceil(.95*len(samples))-1]/1000,
                    p99_us=samples[math.ceil(.99*len(samples))-1]/1000,
                    cpu_seconds=(u1+s1-u0-s0)/os.sysconf("SC_CLK_TCK"),**counts)


if sys.argv[5:] == ["--random"]:
    with (output / "runs.jsonl").open("x") as rows:
        for pair in range(1,7):
            ports = bench.allocate_ports()
            for enabled in ((False,True) if pair%2 else (True,False)):
                row = repeated_seeks(output / f"{pair}-{enabled}",ports,pair)
                print(json.dumps(row), file=rows, flush=True)
    sys.exit(0)

paired.mounted = policy_mount
with (output / "runs.jsonl").open("x") as rows:
    on_ring = sys.argv[5:] == ["--ring-stream"]
    for enabled in (() if on_ring else (False, True)):
        result = check_seeks(output / f"verify-{enabled}", bench.allocate_ports())
        print(json.dumps(dict(policy=enabled, checked_preads=384, **result)), file=rows, flush=True)
    for pair in range(1, 7):
        ports = bench.allocate_ports()
        for enabled in ((False, True) if pair % 2 else (True, False)):
            folder = output / f"{pair}-policy-{enabled}"
            folder.mkdir()
            row = paired.measure(args, folder, pair, on_ring, "fuse-4-read-64", ports)
            print(json.dumps(dict(policy=enabled, **row)), file=rows, flush=True)
