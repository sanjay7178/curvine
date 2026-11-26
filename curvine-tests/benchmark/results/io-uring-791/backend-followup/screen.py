"""Run the prototype screens against the released server and LocalFile."""
import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


def run(args):
    harness = args.root / "src/curvine-tests/benchmark/worker-io-uring-paired.py"
    spec = importlib.util.spec_from_file_location("paired", harness)
    paired = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(paired)

    dest = args.root / args.name
    dest.mkdir(exist_ok=True)
    servers = {arm: args.root / f"{arm}-server" for arm in args.arms}
    servers["old"] = args.reference / "curvine-server"
    control = "wake" if "wake" in args.arms else next(arm for arm in args.arms if arm != "off")
    servers["off"] = servers[control]
    for arm in args.arms:
        (dest / arm).mkdir(exist_ok=True)

    results = dest / "rows.jsonl"
    with results.open("a") as output:
        previous = [json.loads(line) for line in results.read_text().splitlines()]
        finished = {(r["pair"], r["cell"], r["arm"]) for r in previous}
        for group in range(1, args.pairs + 1):
            for index, cell in enumerate(args.cells):
                ports = paired.bench.allocate_ports()
                order = args.arms if group % 2 else list(reversed(args.arms))
                shift = index % len(order)
                for arm in order[shift:] + order[:shift]:
                    if (group, cell, arm) in finished:
                        continue
                    settings = SimpleNamespace(
                        server=servers[arm],
                        cli=args.reference / "curvine-cli",
                        fuse=args.reference / "curvine-fuse",
                        seconds=args.seconds,
                    )
                    row = paired.measure(settings, dest / arm, group, arm != "off", cell, ports)
                    row["arm"] = arm
                    print(json.dumps(row), file=output, flush=True)
                    print(group, cell, arm, row["result"]["value"], flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("name")
    parser.add_argument("--arms", nargs="+", default=["old", "pool", "off", "wake"])
    parser.add_argument("--cells", nargs="+", default=[
        "client-128-read-64", "fuse-4-read-64", "client-128-write-1", "client-4-read-64",
    ])
    parser.add_argument("--pairs", type=int, default=2)
    parser.add_argument("--seconds", type=int, default=7)
    run(parser.parse_args())
