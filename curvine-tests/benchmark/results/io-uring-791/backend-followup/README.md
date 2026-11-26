# Worker io_uring follow-up for #2497

The final server at `56f0ad72` combines already-buffered small read requests on the Linux worker. Mounted trials used FUSE direct I/O. The worker used buffered file I/O on the ext4 VM. Changes are medians of six paired throughput ratios. The interval spans the six observed ratios, the distribution-free 96.9% interval for the population median under independent pairs. CPU values are worker process user plus system seconds per GiB. [Final trial rows](final.jsonl) · [All prototype summaries](summary.csv) · [Binary hashes](manifest.json)

| Workload | LocalFile → io_uring MiB/s | Paired change (96.9% CI) | p95 ms | p99 ms | Worker CPU s/GiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| SDK 4 KiB read ×64 | 471 → 1,020 | +117.8% (+110.4% to +141.9%) | 680.1 → 297.2 | 680.1 → 297.2 | 11.31 → 4.66 |
| SDK 128 KiB read ×64 | 3,992 → 4,086 | +5.0% (-1.1% to +6.5%) | 131.1 → 125.1 | 131.1 → 125.1 | 1.39 → 1.26 |
| FUSE 4 KiB streaming read ×64 | 388 → 489 | +25.4% (+15.4% to +36.1%) | 874.2 → 661.8 | 874.2 → 661.8 | 11.06 → 6.59 |
| SDK 128 KiB write ×1 | 411 → 335 | -18.2% (-46.8% to +43.0%) | 16.4 → 24.6 | 32.8 → 32.8 | 1.66 → 2.09 |

### Comparison with the previous PR server

| Workload | Previous → final MiB/s | Paired change (96.9% CI) | Groups faster |
| --- | ---: | ---: | ---: |
| SDK 4 KiB read ×64 | 802 → 1,020 | +27.0% (+19.8% to +31.2%) | 6/6 |
| SDK 128 KiB read ×64 | 3,999 → 4,086 | +3.4% (-2.8% to +6.7%) | 5/6 |
| FUSE 4 KiB streaming read ×64 | 388 → 489 | +26.2% (+23.8% to +31.6%) | 6/6 |
| SDK 128 KiB write ×1 | 337 → 335 | +3.6% (-31.0% to +61.0%) | 3/6 |

### Mounted random-open control

The depth-one client opened a file and read one random 4 KiB page with each request. Six pairs ran on the final executables. Each arm checked the contents of 256 pages per cache condition.

| Guest page cache | LocalFile → io_uring IOPS | Paired change (96.9% CI) | p99 µs |
| --- | ---: | ---: | ---: |
| guest-cold-advised | 4,759 → 5,010 | +4.3% (-9.1% to +15.2%) | 6,033 → 5,995 |
| warm | 6,326 → 6,287 | +0.8% (-10.5% to +13.1%) | 4,064 → 3,763 |

## Correctness checks

The final binary passed SDK-to-FUSE and FUSE-to-SDK SHA-256 readback on both backends. The ring accounted for all 11,534,973 read bytes and 7,340,412 write bytes on the enabled worker. The disabled worker recorded zero ring bytes. The release test run passed 70 RPC tests, 166 local-storage tests, four real-ring worker TCP tests and the real-ring worker dispatch test. It covered ordered replies, partial headers, seek boundaries, a truncated file with a readable prefix, staged checkpoints, cancellation and restart. [Cross-path hashes](sdk-fuse-hashes.json)

## What changed in the worker

The receive buffer can contain several complete requests for the same open block. For an eligible ring reader, the worker combines up to four consecutive requests of at most 4 KiB into one positional read. It preserves the response for each request and its original sequence ID. A different request ID, code or status, a seek header, a payload or a partial frame ends the group. The worker limits the group to full chunks within the advertised extent. If a combined exact read fails, individual reads recover any readable prefix at the original cursor.

A separate, instrumented mounted run counted 365,949 completed ring reads for 840,704 application-requested 4 KiB chunks, a 56.5% reduction in submissions. The kernel reported 123,047 completions of 4 KiB, 78,589 of 8 KiB, 96,773 of 12 KiB and 67,540 of 16 KiB. These add up to all 3,443,523,584 requested bytes. The trace ran separately from throughput comparisons. [Kernel counters](read-trace-counters.txt)

## What the other prototypes showed

- **Simple buffer reuse.** Recycling 4 KiB and 128 KiB buffers looked promising in the two short FUSE groups. In six 20-second FUSE groups it lost to the previous PR server in five, with a median paired change of −2.0%. The comparison with same-binary LocalFile was −0.1%. At 128 KiB the two short SDK pairs were within 1% of LocalFile.
- **Larger read groups.** Grouping up to four 128 KiB requests caused 101,006–109,287 worker minor faults per GiB and reduced throughput in both pairs. Limiting medium reads to two and recycling 256 KiB buffers cut the fault rate to 414–590/GiB. That variant still trailed the previous PR server in all three pairs, by a median 2.9%, and trailed its same-binary LocalFile control by 3.7%. The retained size limit keeps larger chunks on the individual-read path. [Per-run fault counts](page-faults.csv)
- **Single-writer SDK.** Changing the admission condition variable lost 3.3% to the previous PR server across four paired groups. Tracking the private extent to remove a metadata lookup lost 7.8%. LocalFile won every group against both candidates. In a separate trace of the previous PR server, all 16,384 buffered writes of 128 KiB went through the kernel async-work queue. The mean kernel submission-to-completion interval was 83 µs. This interval excludes SDK, network and userspace response processing. [Kernel counters](trace-counters.txt)
- **Worker CPU.** In a separate 128 KiB SDK run, the previous PR server and LocalFile used 1.29 and 1.35 worker CPU-seconds/GiB. Mounted 4 KiB reads used 8.89 and 10.97 worker CPU-seconds/GiB, and the mount daemons used 8.10 and 8.62. These figures are single diagnostic runs. [Process samples](component.jsonl)

The streaming runs used warm guest pages and loopback networking. They measure SDK or mounted application throughput on this VM. The single-writer test used buffered Complete. Storage and worker TCP tests separately cover explicit Flush, cancellation, disconnect and restart. The NVMe peer was unavailable for this round.

## Method and replay

These experiments use the stock SDK and FUSE daemon from `d06f3aae`. The host is a 16-vCPU Linux 7.0 ext4 VM on virtio storage. The client, mount and cluster share CPUs 0–11. Each trial starts a fresh cluster, prefills 64 files of 4 MiB, warms up for two seconds, then runs a single workload. All streaming figures use application MiB/s. p95 and p99 cover complete 4 MiB file operations. The CLI reports histogram percentiles, so the two tails can occupy the same bucket.

## Worker prototypes

| Arm | Change |
| --- | --- |
| old | Release server from the published PR commit. |
| off | LocalFile. The short screen and write follow-up use the wake binary with the backend disabled. The longer FUSE confirmation uses the pool binary with the backend disabled. The process CPU diagnostic uses the original PR binary. |
| pool | Recycle matching 4 KiB and 128 KiB buffers under the existing 16-buffer cache limit, alongside 1 MiB buffers. Release the buffer after the last response slice drops. |
| wake | Use a parking_lot mutex and condition variable for blocking admission. Preserve the existing 64-operation limit, async notification and ring selection. |
| burst | Combine up to four adjacent headerless read frames already in the receive buffer. Preserve one response and one sequence ID per request. Maximum grouped I/O was 1 MiB. |
| small | Limit the same optimization to individual chunks of at most 4 KiB. Group at most four complete chunks within the logical extent. |
| midpair | Add two-frame grouping for 128 KiB and reuse 256 KiB buffers. The patch applies on top of the small variant. |
| extent | Track the private inode extent after each successful write. Preserve first-view inode validation and copy-on-overwrite semantics. |

The initial screen used two groups per workload and a seven-second window. The separate write comparison used four interleaved groups, a 20-second limit and a 2 GiB cap per arm. Each arm in the longer write comparison reached the cap. The FUSE confirmation used six interleaved triples, reversing order each group, with a 20-second window. The demand screen used two groups of eight-second reads. The medium-chunk follow-up used three groups of 12-second reads. The final matrix used six groups of all three arms per workload. Each workload runs all six arm orders. All final arms used the same final CLI and FUSE binaries. The previous-head arm changed only the server binary. The summary reports the median of the within-group throughput changes. The component CPU measurements and traced write ran separately. The first screen's 4 KiB SDK old and pool measurements overlapped a trace attachment check filtered to an unused process ID. Those two observations are exploratory.

## Reproduce

Use a Linux host with working io_uring, an ext4 data directory, a working Curvine FUSE mount, and permission to run the mount helper. Create a working directory and check out the source commit in its `src` subdirectory. Build the original server, CLI, and FUSE release executables and copy them into a `reference` subdirectory. Apply each of the pool, wake and extent patches to a fresh copy of that commit. Build `cargo build --locked --release -p curvine-server --bin curvine-server` and save the resulting server as `pool-server`, `wake-server` or `extent-server` in the working directory. Build the burst server by applying `burst.patch` to the original commit. Build the medium-pair server by applying `midpair-extra.patch` to the small variant. Save these as `burst-server` and `midpair-server` in the working directory. Build the final checkout and place its release server, CLI and FUSE binaries in the `final-bin` subdirectory. The runner imports the benchmark harness from `src`. Run the following commands from the directory containing the attached scripts, with the absolute working directory in `run`.

```bash
taskset -c 0-11 python3 screen.py "$run" "$run/reference" screen
taskset -c 0-11 python3 screen.py "$run" "$run/reference" writes \
  --arms extent old off wake --cells client-128-write-1 --pairs 4 --seconds 20
taskset -c 0-11 python3 screen.py "$run" "$run/reference" demand \
  --arms burst old off --cells client-128-read-64 fuse-4-read-64 client-4-read-64 --pairs 2 --seconds 8
taskset -c 0-11 python3 screen.py "$run" "$run/reference" mid \
  --arms midpair old off --cells client-128-read-64 --pairs 3 --seconds 12
taskset -c 0-11 python3 final-matrix.py "$run" "$run/reference"
taskset -c 0-11 python3 hash.py "$run"
taskset -c 0-11 python3 trace.py "$run" "$run/reference"
taskset -c 0-11 python3 trace-read.py "$run" "$run/reference"
taskset -c 0-11 python3 cpu.py "$run" "$run/reference"
taskset -c 0-11 python3 screen.py "$run" "$run/reference" confirm \
  --arms pool old off --cells fuse-4-read-64 --pairs 6 --seconds 20
```

For the random control, run the existing [mounted random-open harness](../backend-only/random-mounted.py) with the final binary directory and an empty output path. The trace requires bpftrace and kernel tracepoint access. It keys write latency on the kernel request, from submission to CQE, including time queued for async work. The diagnostic captures only requests submitted by the selected worker. The [Linux write path](https://github.com/torvalds/linux/blob/v7.0/io_uring/rw.c#L1079-L1087) checks filesystem support before attempting a nonblocking buffered write. The [3FS read worker](https://github.com/deepseek-ai/3FS/blob/main/src/storage/aio/AioReadWorker.cc) initializes ring resources with descriptors and I/O vectors and processes batches. The Curvine pool experiment tests ordinary owned memory reuse while preserving the TCP response lifetime.
