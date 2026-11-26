"""Summarize a release worker libtest replay. Run with raw/ and the result directory."""
import csv
import json
import math
import sys
from pathlib import Path
from statistics import median


def check(condition, label):
    if not condition:
        raise ValueError(label)


def worker_summary(raw, dest):
    summary = []
    for group, count, controls in [("worker-reads", 72, ["local_file"]), ("worker-writes", 36, ["local_file", "staged_pwrite"]),
                                   ("worker-copy", 24, ["copied_ring"])]:
        rows = [json.loads(l) for l in (raw / (group + ".jsonl")).read_text().splitlines()]
        check(len(rows) == count, group)
        read = group == "worker-reads"
        expected_arms = {"async_ring", "blocking_ring", "local_file"} if read else set(controls + ["io_uring"])
        expected_cells = {(k, t) for k in (("warm_sequential", "cold_advised_random") if read else ("write",)) for t in (1, 16)}
        groups = {}
        for r in rows:
            w = r["worker"]
            size = r["bytes_verified"] if read else r["bytes_completed"]
            flow = "read" if read else "write"
            check(size == w[flow + "_bytes"] > 0 and r["filesystem"] == "ext4", (group, flow, size))
            check(w["io_uring_" + flow + "_bytes"] == (size if r["variant"] in ("async_ring", "blocking_ring", "copied_ring", "io_uring") else 0), r["variant"])
            if read:
                check(r["blocks_seeded"] == 128 and r["running_rpc_count"] > 0, (group, r["repetition"]))
                p95, p99 = r["running_rpc_p95_ns"], r["running_rpc_p99_ns"]
            else:
                check(w["verified_block_count"] == w["finalized_block_count"] == r["blocks_completed"] == 128, group)
                check(not r["explicit_flush"] and w["shared_write_bytes"] == (size if r["variant"] == "io_uring" else 0), group)
                lat = sorted(r["complete_rpc_ns"])
                check(len(lat) == 128, group)
                p95, p99 = [lat[math.ceil(len(lat)*q)-1] for q in (.95, .99)]
            k = (r.get("workload", "write"), r["clients"])
            reps = groups.setdefault(k, {}).setdefault(r["repetition"], {})
            check(r["variant"] not in reps, group)
            reps[r["variant"]] = dict(rate=r["mib_per_sec"], cpu_s_per_gib=r["worker_cpu_seconds"] * 2**30 / size,
                                      p95_ms=p95/1e6, p99_ms=p99/1e6)
        check(set(groups) == expected_cells, group)
        for (label, clients), reps in groups.items():
            check(set(reps) == set(range(1, 7)) and all(set(x) == expected_arms for x in reps.values()), group)
            candidate = "async_ring" if read else "io_uring"
            for control in controls:
                changes = [100 * (x[candidate]["rate"]/x[control]["rate"] - 1) for x in reps.values()]
                s = dict(suite=group,workload=label,clients=clients,baseline=control,candidate=candidate,pairs=6,
                         wins=sum(x>0 for x in changes),change_pct=median(changes),min_pct=min(changes),max_pct=max(changes))
                for key in ("rate", "p95_ms", "p99_ms", "cpu_s_per_gib"):
                    s["baseline_"+key] = median(x[control][key] for x in reps.values())
                    s["candidate_"+key] = median(x[candidate][key] for x in reps.values())
                summary.append(s)
    check(len(summary) == 10, len(summary))
    with (dest / "worker-controls.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=summary[0].keys(), lineterminator="\n")
        w.writeheader()
        for row in summary:
            w.writerow({k: round(v, 8) if isinstance(v, float) else v for k,v in row.items()})


if __name__ == "__main__":
    worker_summary(Path(sys.argv[1]), Path(sys.argv[2]))
