"""Summarize six matched runs per comparison using paired throughput ratios."""
import csv
import json
import math
from pathlib import Path
from statistics import median

root = Path(__file__).resolve().parent
samples = {}


def load(name):
    with (root / name).open() as source:
        return [json.loads(line) for line in source]


def record(cell, pair, enabled, rate, p95_ms, p99_ms, cpu_seconds, size):
    by_pair = samples.setdefault(cell, {}).setdefault(pair, {})
    if enabled in by_pair:
        raise ValueError(f"duplicate entry for {cell}, pair {pair}, arm {enabled}")
    by_pair[enabled] = (rate, p95_ms, p99_ms, cpu_seconds / (size / 2**30))


def streaming(row, cell, enabled):
    result = row["result"]
    record(cell, row["pair"], enabled, result["value"], result["latency_p95_ms"],
           result["latency_p99_ms"], row["cpu_seconds"], row["worker_bytes"])


for row in load("e2e.jsonl"):
    streaming(row, row["cell"], row["enabled"])
for row in load("mounted-random.jsonl"):
    record("random-open-" + row["cache"], row["pair"], row["enabled"], row["iops"],
           row["p95_us"]/1000, row["p99_us"]/1000, row["cpu_seconds"], row["application_bytes"])
for row in load("fuse-random.jsonl"):
    record("FUSE-policy-on-vs-default-repeated-seek", row["pair"], row["policy"], row["iops"],
           row["p95_us"]/1000, row["p99_us"]/1000, row["cpu_seconds"], row["application_bytes"])
for row in load("sdk-batching.jsonl"):
    streaming(row, "SDK-batch-four-vs-one-" + row["cell"], row["depth"] == 4)
for row in load("fuse-ring-stream.jsonl"):
    streaming(row, "FUSE-policy-on-vs-default-ring", row["policy"])
for row in load("fuse-policy.jsonl"):
    if "result" in row:
        streaming(row, "FUSE-policy-on-vs-default-LocalFile", row["policy"])
for row in load("worker-reads.jsonl"):
    if row["variant"] == "blocking_ring":
        continue
    record(f"worker-{row['workload']}-{row['clients']}", row["repetition"],
           row["variant"] == "async_ring", row["mib_per_sec"], row["running_rpc_p95_ns"]/1e6,
           row["running_rpc_p99_ns"]/1e6, row["worker_cpu_seconds"], row["bytes_verified"])

for file, comparisons in (("worker-writes.jsonl", [("local_file", "io_uring"), ("staged_pwrite", "io_uring")]),
                          ("worker-copy.jsonl", [("copied_ring", "io_uring")])):
    for row in load(file):
        lat = sorted(row["complete_rpc_ns"])
        for baseline, candidate in comparisons:
            if row["variant"] in (baseline, candidate):
                record(f"worker-write-vs-{baseline}-{row['clients']}", row["repetition"],
                       row["variant"] == candidate, row["mib_per_sec"],
                       lat[math.ceil(len(lat)*.95)-1]/1e6, lat[math.ceil(len(lat)*.99)-1]/1e6,
                       row["worker_cpu_seconds"], row["bytes_completed"])

with (root / "summary.csv").open("w") as out:
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["case", "pairs", "baseline_rate", "candidate_rate", "change_pct",
                     "ci_low_pct", "ci_high_pct", "baseline_p95_ms", "candidate_p95_ms",
                     "baseline_p99_ms", "candidate_p99_ms", "baseline_cpu_s_gib", "candidate_cpu_s_gib"])
    for case, pairs in samples.items():
        assert len(pairs) == 6 and all(set(pair) == {True, False} for pair in pairs.values())
        off, on = [[pair[arm] for pair in pairs.values()] for arm in (False, True)]
        ratios = [100 * (b[0]/a[0] - 1) for a, b in zip(off, on)]
        stats = [median(a[0] for a in off), median(b[0] for b in on),
                 median(ratios), min(ratios), max(ratios)]
        for i in (1, 2, 3):
            stats.extend([median(a[i] for a in off), median(b[i] for b in on)])
        writer.writerow([case, len(pairs)] + [round(x, 4) for x in stats])
