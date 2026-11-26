# Curvine PR benchmark rerun

The E2E suite on 2026-11-26 ran from 17:18:12 to 18:05:35 UTC. The 11 workloads contributed 156 timed observations, including 24 runs of the previous #2497 server.

[E2E summary](summary.csv) · [Per-pair results](pairs.csv) · [Previous worker](previous-server.csv) · [Worker TCP controls](worker-controls.csv) · [Binary and host manifest](manifest.json)

The 16-vCPU AMD EPYC-Rome KVM guest used ext4 on virtio storage and Linux 7.0.0-38-generic. The cluster, CLI and mount shared CPUs 0–11 over loopback. A single benchmark occupied the host at a time. The NVMe peer was offline. Streaming reads used warm guest pages. Mounted reads used FUSE direct I/O over a buffered worker.

Rates are the separate medians for each arm, in MiB/s or IOPS. Each change is the median of six matched throughput ratios. The range is the lowest and highest observed percentage change. Wins count the pairs in which the candidate was faster.

## E2E throughput

### #2497 · Worker, same-binary LocalFile → io_uring

| Workload | Baseline → candidate | Unit | Rerun | Six-pair range | Wins | Prior run |
|---|---|---|---|---|---|---|
| SDK 4 KiB read ×64 | 523.8 → 974.8 | MiB/s | +88.1% | +65.0% to +116.7% | 6/6 | +117.8% |
| SDK 128 KiB read ×64 | 3,926.8 → 3,997.7 | MiB/s | +1.8% | -5.4% to +6.8% | 4/6 | +5.0% |
| FUSE 4 KiB streaming read ×64 | 380.7 → 488.3 | MiB/s | +29.5% | +23.4% to +37.2% | 6/6 | +25.4% |
| SDK 128 KiB write ×1 | 361.4 → 292.1 | MiB/s | -18.5% | -40.2% to +12.2% | 1/6 | -18.2% |
| FUSE random open ×16, guest-cold-advised | 4,583.8 → 4,691.0 | IOPS | +0.1% | -12.9% to +21.6% | 3/6 | +4.3% |
| FUSE random open ×16, warm | 6,395.1 → 6,125.3 | IOPS | -0.6% | -8.5% to +1.3% | 2/6 | +0.8% |


### #2584 · SDK, one → four chunks per write RPC on LocalFile

| Workload | Baseline → candidate | Unit | Rerun | Six-pair range | Wins | Prior run |
|---|---|---|---|---|---|---|
| SDK 128 KiB write ×1 | 392.0 → 562.2 | MiB/s | +43.0% | -12.6% to +101.0% | 5/6 | +29.9% |
| SDK 128 KiB write ×16 | 1,546.7 → 1,574.9 | MiB/s | +3.5% | -16.2% to +31.7% | 3/6 | +7.7% |


### #2585 · FUSE, default → opt-in bounded prefetch on seek

| Workload | Baseline → candidate | Unit | Rerun | Six-pair range | Wins | Prior run |
|---|---|---|---|---|---|---|
| FUSE 4 KiB stream ×64, LocalFile | 387.4 → 398.0 | MiB/s | +4.5% | -10.1% to +12.7% | 4/6 | +1.6% |
| FUSE 4 KiB stream ×64, io_uring | 383.9 → 395.9 | MiB/s | +2.4% | +0.7% to +5.4% | 6/6 | +2.2% |
| FUSE 4 KiB repeated seek ×16, LocalFile | 23,029.7 → 35,717.1 | IOPS | +48.2% | +34.2% to +63.0% | 6/6 | +43.1% |


## Tails, CPU and data requests

p95 and p99 are medians of per-trial latencies in milliseconds. The streaming histogram times a complete 4 MiB file operation, so p95 and p99 can occupy the same bucket. Random-open times include open, one 4 KiB pread and close. Repeated-seek times cover one pread on an open file. CPU is the worker process’s user plus system seconds per application GiB.

| PR | Workload | p95 ms | p99 ms | Worker CPU s/GiB | Worker data requests/GiB |
|---|---|---|---|---|---|
| 2497 | SDK 4 KiB read ×64 | 604.65 → 309.51 | 604.65 → 309.51 | 10.39 → 4.82 | 262,144 → 262,144 |
| 2497 | SDK 128 KiB read ×64 | 131.07 → 131.07 | 131.07 → 131.07 | 1.36 → 1.27 | 8,192 → 8,192 |
| 2497 | FUSE 4 KiB streaming read ×64 | 901.47 → 673.80 | 901.47 → 673.80 | 11.26 → 6.57 | 262,144 → 262,144 |
| 2497 | SDK 128 KiB write ×1 | 16.38 → 32.77 | 32.77 → 32.77 | 1.87 → 2.31 | 8,192 → 8,192 |
| 2497 | FUSE random open ×16, guest-cold-advised | 5.17 → 5.07 | 6.15 → 6.14 | 66.56 → 61.44 | 267,776 → 269,824 |
| 2497 | FUSE random open ×16, warm | 3.26 → 3.28 | 3.66 → 3.90 | 51.20 → 46.08 | 271,872 → 272,896 |
| 2584 | SDK 128 KiB write ×1 | 24.57 → 16.38 | 32.77 → 32.77 | 1.63 → 1.13 | 8,192 → 2,302 |
| 2584 | SDK 128 KiB write ×16 | 131.07 → 131.07 | 179.88 → 149.05 | 1.78 → 1.33 | 8,192 → 2,264 |
| 2585 | FUSE 4 KiB stream ×64, LocalFile | 832.40 → 817.93 | 832.40 → 817.93 | 11.05 → 10.72 | 262,144 → 262,144 |
| 2585 | FUSE 4 KiB stream ×64, io_uring | 908.83 → 803.62 | 908.83 → 803.62 | 8.86 → 8.48 | 262,144 → 262,144 |
| 2585 | FUSE 4 KiB repeated seek ×16, LocalFile | 1.12 → 0.76 | 1.52 → 1.04 | 44.48 → 14.88 | 1,039,312 → 264,928 |

## Current worker vs previous #2497 io_uring server

| Workload | Previous → current MiB/s | Paired change | Six-pair range | Wins |
|---|---|---|---|---|
| SDK 4 KiB read ×64 | 753.2 → 974.8 | +26.6% | +23.2% to +35.6% | 6/6 |
| SDK 128 KiB read ×64 | 3,947.3 → 3,997.7 | -0.3% | -4.1% to +8.5% | 2/6 |
| FUSE 4 KiB streaming read ×64 | 392.8 → 488.3 | +23.5% | +22.9% to +26.1% | 6/6 |
| SDK 128 KiB write ×1 | 293.3 → 292.1 | -11.9% | -29.1% to +39.1% | 2/6 |


## Worker TCP and copy controls

A separate release worker test binary built from the #2497 head ran 132 timed observations over a TCP block client. These cover the worker data path directly. Each arm used 128 blocks and six repetitions. The read rows time data RPCs and the write rows time buffered Complete for latency. The owned-write comparison changes the copy path on the same ring backend. Worker data and routing counters were verified for all observations. The raw read rows also retain the blocking-ring reference.

| Workload | Clients | Baseline → candidate | MiB/s | Paired change | Six-pair range | Wins |
|---|---|---|---|---|---|---|
| warm sequential | 1 | local_file → async_ring | 731.0 → 663.3 | -8.6% | -18.6% to -0.1% | 0/6 |
| warm sequential | 16 | local_file → async_ring | 2,973.4 → 3,046.4 | +0.4% | -9.5% to +18.0% | 3/6 |
| cold advised random | 1 | local_file → async_ring | 11.2 → 9.3 | -12.6% | -22.3% to +6.2% | 1/6 |
| cold advised random | 16 | local_file → async_ring | 57.8 → 59.5 | +7.3% | -12.1% to +9.0% | 4/6 |
| write | 1 | local_file → io_uring | 914.2 → 769.8 | -13.9% | -24.6% to -7.3% | 0/6 |
| write | 1 | staged_pwrite → io_uring | 829.1 → 769.8 | -4.0% | -11.6% to +6.0% | 2/6 |
| write | 16 | local_file → io_uring | 2,654.9 → 2,542.0 | -8.0% | -21.2% to +12.9% | 2/6 |
| write | 16 | staged_pwrite → io_uring | 2,384.4 → 2,542.0 | +5.3% | -18.2% to +41.0% | 4/6 |
| write | 1 | copied_ring → io_uring | 695.2 → 805.7 | +14.2% | +7.9% to +27.0% | 6/6 |
| write | 16 | copied_ring → io_uring | 2,076.8 → 2,326.0 | +11.0% | +4.0% to +29.6% | 6/6 |


## Correctness and benchmark controls

- The CLI reported zero operation errors. Every timed streaming arm delivered the reported application bytes through the worker. The enabled worker accounted for every measured data byte through io_uring. LocalFile reported zero ring bytes. Streaming and SDK write trials verified two active worker rings when enabled and zero when disabled.
- Deterministic SDK-to-FUSE and FUSE-to-SDK SHA-256 readbacks matched on both backends. Each backend served 11,534,973 read bytes and 7,340,412 write bytes in that check.
- Mounted random-open compared all 6,144 returned pages with expected bytes. The repeated-seek workload checked 98,304 pages. The separate seek-then-sequential checks verified another 384 preads with each policy.
- The backend streaming and write matrix rotated all six arm orders. Standalone policy and random-open trials balanced their two orders three times each. The #2497 LocalFile and io_uring arms shared executables. The #2584 and #2585 comparisons used the same client executable on both sides and held their worker fixed.
- The SDK and streaming runs seeded 64 files of 4 MiB and warmed up for two seconds. The worker matrix used 20-second read windows. Standalone FUSE streaming used 10 seconds. SDK writes used buffered Complete and a 2 GiB stopping threshold. Concurrent writers can finish already-started files after reaching that threshold. The reported throughput uses actual completed bytes and elapsed time.
- For guest-cold-advised random opens, Linux charged 1.07–1.54 MiB of storage reads to the worker per 1 MiB of application reads. Cold advice applies to the guest page cache.
- For warm random opens, Linux charged 0.00–0.00 MiB of storage reads to the worker per 1 MiB of application reads. Cold advice applies to the guest page cache.

| Correctness tests run after timings | Passed |
|---|---|
| Worker TCP with a real ring, including Flush, cancel, disconnect and restart | 4 |
| Local storage unit tests, including real-ring cases | 166 |
| SDK raw RPC client tests, including gathered timeout and reply order | 7 |
| SDK write framing | 1 |
| FUSE seek limit on both reader paths | 1 |

## Source and replay

- [PR #2497](https://github.com/CurvineIO/curvine/pull/2497) at `56f0ad726901a4cfc84e18b51ad173bf473452c9`.
- [PR #2584](https://github.com/CurvineIO/curvine/pull/2584) at `c1cf6cf0c624e80ac7da4accd6aebd9b52ebd294`.
- [PR #2585](https://github.com/CurvineIO/curvine/pull/2585) at `cccb6193f7e74aca1e0ecb8b9bf4f10c681efbd9`.

The archived backend binaries matched all six published SHA-256 digests. The standalone SDK CLI and FUSE daemon were rebuilt in release mode from the PR heads. The manifest records all eight executable digests and the previous worker commit. The standalone workloads use that previous worker, held fixed in both arms, as in the published comparison.

To recompute the four summary CSVs from this directory, run `python3 summarize.py raw recomputed` and `python3 worker_summary.py raw recomputed`. The [raw trial rows](raw) and [correctness test outcomes](checks) are available alongside the summaries.

To replay the E2E timings on a comparable Linux host, copy `rerun.sh` into a fresh scratch directory on ext4. Inside that directory, create a symlink named `src` pointing to the root of this benchmark checkout. Place the release executables under `final-bin`, `reference` and `policy-bin` using the filenames and source revisions in the manifest. Run `bash ./rerun.sh` from the scratch directory. The harness uses sudo to mount and unmount FUSE.

The worker controls use the following commands in the #2497 checkout. Set the data directory to an ext4 scratch directory with sufficient space.

```sh
export CURVINE_WRITE_BENCH_DIR=/var/tmp
export CURVINE_READ_BENCH_BLOCKS=128 CURVINE_READ_BENCH_REPS=6
export CURVINE_WRITE_BENCH_BLOCKS=128 CURVINE_WRITE_BENCH_REPS=6 CURVINE_WRITE_BENCH_VERIFY=1
cargo test --locked --release -p curvine-worker --lib --no-run
taskset -c 0-11 cargo test --locked --release -p curvine-worker --lib worker_read_ablation -- --ignored --nocapture
taskset -c 0-11 cargo test --locked --release -p curvine-worker --lib worker_write_ablation -- --ignored --nocapture
CURVINE_WRITE_BENCH_COMPARE_COPY=1 taskset -c 0-11 cargo test --locked --release -p curvine-worker --lib worker_write_ablation -- --ignored --nocapture
```
