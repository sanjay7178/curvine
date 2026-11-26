#!/usr/bin/env bash
set -euo pipefail
d="$(cd "$(dirname "$0")" && pwd)"
p="$d/src/curvine-tests/benchmark/results/io-uring-791"
export PYTHONDONTWRITEBYTECODE=1
exec 9>/var/tmp/curvine-pr-e2e-bench.lock
flock -n 9 || { echo "Another benchmark holds the host lock"; exit 1; }
test -x "$d/policy-bin/sdk-cli" && test -x "$d/policy-bin/curvine-fuse"
run_stage() {
    local stage="$1"
    shift
    echo "$(date -u +%FT%TZ) start $stage"
    if taskset -c 0-11 python3 "$@" >"$d/$stage.log" 2>&1; then
        echo "$(date -u +%FT%TZ) finished $stage"
    else
        echo "$(date -u +%FT%TZ) failed $stage"
        tail -15 "$d/$stage.log"
        return 1
    fi
}
run_stage hash "$p/backend-followup/hash.py" "$d"
run_stage sdk-batching "$p/backend-only/sdk-batching.py" "$d/reference" "$d/policy-bin/sdk-cli" "$d/sdk-batching"
run_stage fuse-policy "$p/backend-only/fuse-policy.py" "$d/reference/curvine-server" "$d/reference/curvine-cli" "$d/policy-bin/curvine-fuse" "$d/fuse-policy"
run_stage fuse-ring-stream "$p/backend-only/fuse-policy.py" "$d/reference/curvine-server" "$d/reference/curvine-cli" "$d/policy-bin/curvine-fuse" "$d/fuse-ring-stream" --ring-stream
run_stage fuse-random "$p/backend-only/fuse-policy.py" "$d/reference/curvine-server" "$d/reference/curvine-cli" "$d/policy-bin/curvine-fuse" "$d/fuse-random" --random
run_stage final-matrix "$p/backend-followup/final-matrix.py" "$d" "$d/reference"
run_stage mounted-random "$p/backend-only/random-mounted.py" "$d/final-bin" "$d/mounted-random"
