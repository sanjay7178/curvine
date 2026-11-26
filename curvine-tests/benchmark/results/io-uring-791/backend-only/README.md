# Backend-only io_uring results

Source commit `d06f3aae`. All primary comparisons used the same release executables with only the backend switched. Streaming and worker rates are MiB/s. Mounted random-open rates are IOPS. Each row summarizes six matched pairs.

## End to end on the ext4 VM

| Workload | Rate, off → on | Paired change (96.9% CI) | p95 ms | p99 ms | Worker CPU s/GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| SDK read, 4 KiB ×64 | 502.9 → 781.3 | +51.9% (+35.4% to +81.3%) | 654.84 → 387.27 | 654.84 → 387.27 | 10.64 → 6.64 |
| SDK read, 128 KiB ×64 | 3,938.1 → 4,012.2 | +2.2% (-3.6% to +7.4%) | 128.69 → 126.78 | 128.69 → 126.78 | 1.38 → 1.26 |
| FUSE read, 4 KiB ×64 | 404.1 → 387.8 | -4.0% (-10.7% to +6.5%) | 813.16 → 844.89 | 813.16 → 844.89 | 10.64 → 8.71 |
| SDK write, 128 KiB ×1 | 370.9 → 322.6 | -7.6% (-48.8% to +28.6%) | 24.57 → 32.77 | 32.77 → 32.77 | 1.88 → 2.12 |
| Mounted random open, guest cold | 4,991.0 → 4,882.3 | -1.1% (-9.9% to +7.1%) | 4.65 → 4.48 | 5.76 → 5.63 | 71.68 → 71.68 |
| Mounted random open, warm | 6,334.6 → 6,505.4 | +2.2% (-13.3% to +12.2%) | 3.18 → 3.28 | 3.82 → 3.78 | 51.20 → 46.08 |

For guest-cold-advised mounted reads, each arm verified 1 MiB of random pages. Linux charged 1.07–1.71 MiB of storage reads to the worker per trial. The worker issued 257–270 data requests for the 256 opens. Every worker data byte used the ring in enabled arms and LocalFile in their controls.
For warm mounted reads, each arm verified 1 MiB of random pages. Linux charged 0.00–0.00 MiB of storage reads to the worker per trial. The worker issued 258–272 data requests for the 256 opens. Every worker data byte used the ring in enabled arms and LocalFile in their controls.

## TCP worker and copy controls

Rates are MiB/s. LocalFile is the baseline except where the row specifies the staged-pwrite or copied-ring control. Read latency measures the data RPC. Write latency measures Complete.

| Workload | Rate, off → on | Paired change (96.9% CI) | p95 ms | p99 ms | Worker CPU s/GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| warm sequential-1 | 808.1 → 695.5 | -14.1% (-23.2% to +4.3%) | 0.16 → 0.19 | 0.20 → 0.24 | 1.12 → 1.20 |
| warm sequential-16 | 2,984.6 → 2,881.2 | -5.8% (-17.0% to +49.3%) | 0.91 → 0.98 | 1.88 → 1.84 | 1.36 → 1.20 |
| cold advised random-1 | 11.5 → 9.8 | -12.5% (-30.2% to -5.9%) | 0.23 → 0.26 | 0.33 → 0.34 | 61.44 → 61.44 |
| cold advised random-16 | 64.3 → 67.8 | +4.8% (-1.8% to +12.5%) | 0.73 → 0.55 | 1.00 → 0.67 | 61.44 → 61.44 |
| write-vs-local file-1 | 865.6 → 776.1 | -11.1% (-12.7% to -5.7%) | 0.23 → 0.23 | 0.32 → 0.34 | 1.04 → 1.12 |
| write-vs-staged pwrite-1 | 825.3 → 776.1 | -7.0% (-16.4% to +12.7%) | 0.24 → 0.23 | 0.39 → 0.34 | 1.08 → 1.12 |
| write-vs-local file-16 | 2,905.6 → 2,390.0 | -17.1% (-26.1% to -3.9%) | 2.80 → 2.54 | 3.54 → 3.60 | 1.72 → 1.88 |
| write-vs-staged pwrite-16 | 2,493.4 → 2,390.0 | -3.8% (-20.4% to +1.6%) | 2.81 → 2.54 | 3.50 → 3.60 | 1.76 → 1.88 |
| write-vs-copied ring-1 | 689.4 → 802.2 | +15.4% (+12.8% to +20.5%) | 0.24 → 0.23 | 0.41 → 0.30 | 1.28 → 1.08 |
| write-vs-copied ring-16 | 2,072.2 → 2,516.1 | +17.0% (+7.9% to +40.6%) | 2.89 → 2.43 | 4.29 → 3.17 | 2.32 → 1.88 |

## Independent client changes

The worker uses LocalFile except in the explicitly labeled ring streaming control. Both streaming controls change only the FUSE policy. For SDK writes the comparison is one vs four chunks per RPC. For FUSE reads it is the default policy vs the opt-in seek hint. Rates are MiB/s, except the repeated-seek row in IOPS.

| Workload | Rate, off → on | Paired change (96.9% CI) | p95 ms | p99 ms | Worker CPU s/GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| FUSE-policy-on-vs-default-repeated-seek | 22,902.6 → 32,743.1 | +43.1% (+30.5% to +60.7%) | 1.11 → 0.79 | 1.60 → 1.13 | 43.68 → 15.36 |
| SDK-batch-four-vs-one-client-128-write-1 | 444.9 → 561.1 | +29.9% (-15.8% to +59.8%) | 16.38 → 12.29 | 32.77 → 24.57 | 1.40 → 1.09 |
| SDK-batch-four-vs-one-client-128-write-16 | 1,533.7 → 1,537.6 | +7.7% (-8.2% to +95.1%) | 131.07 → 131.07 | 246.44 → 170.74 | 1.58 → 1.29 |
| FUSE-policy-on-vs-default-ring | 385.0 → 391.9 | +2.2% (-1.1% to +7.0%) | 845.83 → 821.16 | 845.83 → 821.16 | 8.66 → 8.34 |
| FUSE-policy-on-vs-default-LocalFile | 386.8 → 389.1 | +1.6% (-6.3% to +4.0%) | 864.86 → 811.81 | 864.86 → 811.81 | 10.85 → 10.75 |

SDK ×1 issued 8,192 → 2,302 worker data RPCs/GiB.

SDK ×16 issued 8,192 → 2,257 worker data RPCs/GiB.

For 8,192 verified random reads per trial on LocalFile, the seek policy changed median worker data requests from 32,478 to 8,279.

The FUSE correctness check compared 384 4 KiB preads with deterministic source bytes per arm, including contiguous reads immediately after each seek. The worker issued 768 data requests at default and 768 with the policy enabled.

## Method and controls

The source for the worker, SDK CLI and FUSE daemon is `d06f3aae`. Release binaries came from a clean checkout with the lockfile enforced. [Binary hashes, kernel and CPU affinity](manifest.json). The research VM used ext4 on a virtio disk, TCP loopback, one replica, one worker and buffered worker I/O. Each process inherited the same 12-vCPU budget, including the two ring threads. Worker data RPCs used TCP. Sendfile, splice, short circuit, write-back FUSE caching and block checksums were disabled in both arms. Client read depth was four for streaming and one for sparse mounted reads. FUSE direct I/O bypasses the mount page cache. Both arms still use buffered I/O on the worker. [Linux FUSE I/O modes](https://docs.kernel.org/filesystems/fuse/fuse-io.html)

Six pairs alternated backend order within each streaming cell, with a fresh cluster per arm and the cell order held fixed across repetitions. Each streaming arm prefilled 64 distinct 4 MiB files and ran a separate two-second workload warmup. The timed client then repeatedly read the same corpus for 20 seconds, including operations already in progress at the deadline. The single-writer control used the same time limit and a 2 GiB byte cap. Reads and writes have separate timers. Read p95/p99 describe a whole 4 MiB application read. CPU is worker user plus system time per application GiB over the invocation. RPC counts refer to data-carrying requests. Metadata and control RPCs are outside that count. Rates come from the client's workload timer. Normalized CPU and latency values are per-arm medians. [fio documents time windows and ramp time](https://fio.readthedocs.io/en/latest/fio_doc.html) and [Ceph reports CPU allocation when benchmarking its storage paths](https://www.ceph.io/en/news/blog/2025/crimson-balance-cpu-part1/).

Each throughput change is the median of six paired percentage differences. The minimum and maximum paired changes form a conservative 96.875% distribution-free confidence interval for the population median under independent continuous pair effects. Six pairs give a wide interval. Operations within a pair share a cluster and are not independent repetitions. A positive central estimate with an interval spanning zero leaves the direction uncertain.

The separate mounted random workload opens 256 distinct files at randomized page offsets using 16 client threads. Every returned 4 KiB page is compared with deterministic input. The timer includes open, pread and close. Cold-advised trials call fsync and POSIX_FADV_DONTNEED on each finalized worker data file. Warm trials read those same files into the guest page cache before measurement. Process storage-read counters distinguish guest I/O from a cached read. The physical host cache state was unavailable. The historical repeated-seek workload still takes the positional fallback and is outside this random-open result. [Linux posix_fadvise manual](https://man7.org/linux/man-pages/man2/posix_fadvise.2.html)

Worker-only trials use release libtest with a real TCP block client and no master or FUSE. The random worker read opens a block at the random offset before the headerless data request. Read timings separate the data RPC from the workload rate, which includes open, verification and complete. Write throughput includes the full block exchange. Write p95/p99 in the summary refer to the Complete acknowledgement; the raw rows also include full block latency samples. All worker write trials verify finalized file contents. The staged-pwrite control holds staging and buffered Complete constant while changing the I/O implementation. The copied-ring control holds the backend constant while changing receive-buffer ownership. The historical 4 MiB size-specific ablation is [reported separately](https://github.com/sanjay7178/curvine/blob/e023c49e/curvine-tests/benchmark/worker-io-uring-write-batching.md#controlled-worker-change). The primary E2E write control uses a 128 KiB chunk. It measures application completion without per-file fsync. Four real-ring worker TCP tests separately verified ordinary and batch writes, restart, buffered Complete and disconnection. All 166 local-storage tests passed, including the three real-ring tests.

## Reproduction

From the backend checkout, build the release CLI, daemon and worker. Use a local ext4 trial directory and run the following commands sequentially. The example CPU set must be available on the test host.

```sh
cargo build --locked --release -p curvine-server -p curvine-cli -p curvine-fuse
taskset -c 0-11 python3 curvine-tests/benchmark/worker-io-uring-paired.py target/release target/paired
cargo test --locked --release -p curvine-worker --lib --no-run
export CURVINE_READ_BENCH_BLOCKS=128 CURVINE_READ_BENCH_REPS=6
export CURVINE_WRITE_BENCH_BLOCKS=128 CURVINE_WRITE_BENCH_REPS=6 CURVINE_WRITE_BENCH_VERIFY=1
taskset -c 0-11 cargo test --locked --release -p curvine-worker --lib worker_read_ablation -- --ignored --nocapture
taskset -c 0-11 cargo test --locked --release -p curvine-worker --lib worker_write_ablation -- --ignored --nocapture
CURVINE_WRITE_BENCH_COMPARE_COPY=1 taskset -c 0-11 cargo test --locked --release -p curvine-worker --lib worker_write_ablation -- --ignored --nocapture
```

The [mounted random driver](random-mounted.py) takes the release binary directory and a new output directory. The [FUSE policy driver](fuse-policy.py) takes the worker server, SDK CLI, standalone FUSE PR executable, and a new output directory. Pass a final `--ring-stream` argument to repeat the streaming comparison with the ring worker held constant, or `--random` for the independent FUSE repeated-seek test. The [SDK batching driver](sdk-batching.py) takes the backend release binary directory, the standalone SDK CLI and a new output directory. These drivers import the backend driver from the benchmark directory. Run `python3 summarize.py` here to reproduce [the full summary](summary.csv) from the adjacent JSONL files.

Per-run data are in [end-to-end](e2e.jsonl), [mounted random](mounted-random.jsonl), [worker reads](worker-reads.jsonl), [worker writes](worker-writes.jsonl), [worker copy ablation](worker-copy.jsonl), [SDK batching](sdk-batching.jsonl), [FUSE streaming policy on LocalFile](fuse-policy.jsonl), [FUSE streaming policy on the ring worker](fuse-ring-stream.jsonl) and [FUSE repeated seeks](fuse-random.jsonl). The known NVMe test peer was offline. Final-head NVMe and cross-host measurements remain open.
