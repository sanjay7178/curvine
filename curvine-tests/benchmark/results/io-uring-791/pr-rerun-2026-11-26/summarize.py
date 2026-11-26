"""Summarize six matched runs per workload. Run with python3 summarize.py RAW OUTPUT."""
import csv
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path
from statistics import median

GIB = 2**30
BACKEND = {
    "client-4-read-64": "SDK 4 KiB read ×64",
    "client-128-read-64": "SDK 128 KiB read ×64",
    "fuse-4-read-64": "FUSE 4 KiB streaming read ×64",
    "client-128-write-1": "SDK 128 KiB write ×1",
}
FILES = {
    "backend": ("backend.jsonl", 72),
    "mounted": ("mounted-open.jsonl", 24),
    "sdk": ("sdk-batching.jsonl", 24),
    "fuse_local": ("fuse-stream-local.jsonl", 14),
    "fuse_ring": ("fuse-stream-ring.jsonl", 12),
    "fuse_seek": ("fuse-seek.jsonl", 12),
}


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(raw):
    datasets = {}
    for name, (file, count) in FILES.items():
        rows = [json.loads(line) for line in (raw / file).read_text().splitlines()]
        check(len(rows) == count, (file, len(rows), count))
        datasets[name] = rows
    return datasets


def metrics(row, ring_enabled):
    if "result" in row:
        result = row["result"]
        application, worker, ring = result["bytes"], row["worker_bytes"], row["ring_bytes"]
        requests = row["data_requests"]
        check(result["errors"] == 0 and result["operations"] * 4 * 2**20 == application, row)
        check(application == worker and row["non_ring_bytes"] == worker - ring, row)
        check(row["rings"] == (2 if ring_enabled else 0), row)
        rate, p95, p99 = result["value"], result["latency_p95_ms"], result["latency_p99_ms"]
    else:
        application, worker, ring = row["application_bytes"], row["read_bytes"], row["worker_io_uring_read_bytes"]
        requests = row["read_count"]
        check(application == 4096 * row["verified_pages"] and worker == 4096 * requests, row)
        rate, p95, p99 = row["iops"], row["p95_us"] / 1000, row["p99_us"] / 1000
    check(ring == (worker if ring_enabled else 0) and application > 0 and requests > 0, row)
    check(all(math.isfinite(x) for x in [rate, p95, p99, row["cpu_seconds"]]), row)
    check(rate > 0 and 0 < p95 <= p99 and row["cpu_seconds"] >= 0, row)
    return dict(rate=rate, p95_ms=p95, p99_ms=p99, cpu_s_per_gib=row["cpu_seconds"] * GIB / application,
                requests_per_gib=requests * GIB / application, worker_bytes_per_app_byte=worker / application)


def summarize(raw, dest):
    sets = load(raw)
    cases, previous, pairs = [], [], []

    def compare(pr, name, workload, unit, baseline, candidate, left, right, ring, output=cases):
        def by_pair(rows):
            rows = list(rows)
            check(sorted(r["pair"] for r in rows) == list(range(1, 7)), (name, workload, rows))
            return {r["pair"]: metrics(r, ring(r)) for r in rows}
        left, right = by_pair(left), by_pair(right)
        changes = []
        for i in range(1, 7):
            a, b = left[i], right[i]
            change = 100 * (b["rate"] / a["rate"] - 1)
            changes.append(change)
            pair = dict(pr=pr, comparison=name, workload=workload, unit=unit, pair=i,
                        baseline=baseline, candidate=candidate, change_pct=change)
            for key in a:
                pair["baseline_" + key] = a[key]
                pair["candidate_" + key] = b[key]
            pairs.append(pair)
        rec = dict(pr=pr, comparison=name, workload=workload, unit=unit, baseline=baseline,
                   candidate=candidate, pairs=6, faster=sum(v > 0 for v in changes),
                   change_pct=median(changes), min_pct=min(changes), max_pct=max(changes))
        for key in left[1]:
            rec["baseline_" + key] = median(a[key] for a in left.values())
            rec["candidate_" + key] = median(a[key] for a in right.values())
        output.append(rec)

    for cell, label in BACKEND.items():
        block = [r for r in sets["backend"] if r["cell"] == cell]
        orders = [tuple(r["arm"] for r in block if r["pair"] == i) for i in range(1, 7)]
        check(Counter(orders) == Counter(itertools.permutations(("off", "small", "old"))), (label, orders))
        check(all(r["enabled"] == (r["arm"] != "off") for r in block), cell)
        for control, compare_name, out in [("off", "worker backend", cases), ("old", "previous PR server", previous)]:
            compare(2497, compare_name, label, "MiB/s", "LocalFile" if control == "off" else "previous io_uring",
                    "current io_uring", (r for r in block if r["arm"] == control),
                    (r for r in block if r["arm"] == "small"), lambda r: r["enabled"], out)

    for cache in ("guest-cold-advised", "warm"):
        rs = [r for r in sets["mounted"] if r["cache"] == cache]
        check(all(r["verified_pages"] == 256 for r in rs), cache)
        for i in range(1, 7):
            check(len({r["input_sha256"] for r in rs if r["pair"] == i}) == 1, (cache, i))
        compare(2497, "worker backend", "FUSE random open ×16, " + cache, "IOPS", "LocalFile", "current io_uring",
                (r for r in rs if not r["enabled"]), (r for r in rs if r["enabled"]), lambda r: r["enabled"])
    for writers in (1, 16):
        rs = [r for r in sets["sdk"] if r["cell"] == f"client-128-write-{writers}"]
        max_bytes = 2 * GIB + (writers - 1) * 4 * 2**20
        check(all(not r["enabled"] and 2 * GIB <= r["result"]["bytes"] <= max_bytes for r in rs), writers)
        compare(2584, "SDK write batching", f"SDK 128 KiB write ×{writers}", "MiB/s", "1 chunk", "4 chunks",
                (r for r in rs if r["depth"] == 1), (r for r in rs if r["depth"] == 4), lambda r: False)

    checks = [r for r in sets["fuse_local"] if "checked_preads" in r]
    check(sorted(r["policy"] for r in checks) == [False, True], checks)
    check(all(r["checked_preads"] == 384 and r["worker_io_uring_read_bytes"] == 0 for r in checks), checks)
    for name, label, is_ring in [("fuse_local", "FUSE 4 KiB stream ×64, LocalFile", False),
                                 ("fuse_ring", "FUSE 4 KiB stream ×64, io_uring", True),
                                 ("fuse_seek", "FUSE 4 KiB repeated seek ×16, LocalFile", False)]:
        rs = [r for r in sets[name] if "pair" in r]
        seek = name == "fuse_seek"
        check(all(r["verified_pages"] == 8192 if seek else r["enabled"] == is_ring for r in rs), name)
        compare(2585, "FUSE seek prefetch", label, "IOPS" if seek else "MiB/s", "default", "seek hint",
                (r for r in rs if not r["policy"]), (r for r in rs if r["policy"]), lambda r: is_ring)

    for name, subset, key in [("sdk", sets["sdk"], "depth"), ("fuse_local", sets["fuse_local"], "policy"),
                              ("fuse_ring", sets["fuse_ring"], "policy"), ("fuse_seek", sets["fuse_seek"], "policy"),
                              ("mounted", sets["mounted"], "enabled")]:
        for group in {r.get("cache", r.get("cell")) for r in subset if "pair" in r}:
            block = [r for r in subset if "pair" in r and r.get("cache", r.get("cell")) == group]
            orders = Counter(tuple(r[key] for r in block if r["pair"] == i) for i in range(1, 7))
            check(len(orders) == 2 and set(orders.values()) == {3}, (name, group, orders))

    dest.mkdir(exist_ok=True, parents=True)
    for filename, records in [("summary.csv", cases), ("previous-server.csv", previous), ("pairs.csv", pairs)]:
        with (dest / filename).open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys(), lineterminator="\n")
            writer.writeheader()
            for record in records:
                writer.writerow({k: round(v, 8) if isinstance(v, float) else v for k, v in record.items()})
    check(len(cases) == 11 and len(previous) == 4 and len(pairs) == 90, "comparison counts")
    return sets


if __name__ == "__main__":
    summarize(Path(sys.argv[1]), Path(sys.argv[2]))
