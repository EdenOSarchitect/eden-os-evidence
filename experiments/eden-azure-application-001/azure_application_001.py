#!/usr/bin/env python3
"""Pilot harness: CONTROL vs conventional CACHE vs verified EDEN reuse.

Each arm runs in a fresh child process through the same loopback HTTP path.
CPU covers both the load generator and service; it is not Azure platform CPU.
"""
from __future__ import annotations
import argparse, hashlib, http.client, json, multiprocessing, os, platform, random
import resource, statistics, subprocess, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

EXP = "EDEN-AZURE-APPLICATION-001"
MODES = ("CONTROL", "CACHE", "EDEN")
WORKLOAD = "http-deterministic-xorshift-v1"
DOMAIN = b"EDEN-VERIFIED-REUSE-V1\0"
POLICY = {
    "policy_id": "EDEN-EXACT-VERIFIED-REUSE-V1",
    "policy_version": "1.0.0",
    "match": "exact canonical workload descriptor SHA-256",
    "verification": "input, output, policy, provenance and record commitment on every hit",
}
PROVENANCE = {
    "experiment": EXP, "producer": "deterministic_work",
    "workload_version": WORKLOAD, "origin": "computed_in_current_arm",
}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode()

def sha_bytes(value): return "sha256:" + hashlib.sha256(value).hexdigest()
def sha(value): return sha_bytes(canonical(value))
def utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def work(seed, iterations):
    value = (seed * 2654435761) & 0xffffffff
    for index in range(iterations):
        value ^= (value << 13) & 0xffffffff
        value ^= value >> 17
        value ^= (value << 5) & 0xffffffff
        value = (value + index * 17) & 0xffffffff
    return value

def descriptor(seed, iterations):
    return {"workload": WORKLOAD, "seed": seed, "iterations": iterations}

def output(seed, value): return {"seed": seed, "value": value}

def make_record(seed, iterations, value):
    core = {
        "schema": "eden.verified_reuse_record.v1",
        "input_commitment": sha(descriptor(seed, iterations)),
        "output_commitment": sha(output(seed, value)),
        "policy": POLICY, "policy_commitment": sha(POLICY),
        "provenance": PROVENANCE, "value": value,
    }
    return {**core, "record_commitment": sha_bytes(DOMAIN + canonical(core))}

def verify_record(record, seed, iterations):
    try:
        core = dict(record)
        claimed = core.pop("record_commitment")
        return all((
            core["schema"] == "eden.verified_reuse_record.v1",
            core["input_commitment"] == sha(descriptor(seed, iterations)),
            core["output_commitment"] == sha(output(seed, int(core["value"]))),
            core["policy"] == POLICY, core["policy_commitment"] == sha(POLICY),
            core["provenance"] == PROVENANCE,
            claimed == sha_bytes(DOMAIN + canonical(core)),
        ))
    except (KeyError, TypeError, ValueError):
        return False

def request_stream(count, reuse, seed):
    unique = max(1, count - int(round(count * reuse)))
    values = list(range(1, unique + 1))
    while len(values) < count:
        values.append(values[(len(values) - unique) % unique])
    random.Random(seed).shuffle(values)
    return values

def percentile(values, fraction):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * fraction) + 0.999999) - 1))
    return ordered[index]

class State:
    """Thread-safe exact cache with per-key single-flight misses."""
    def __init__(self, mode, iterations):
        self.mode, self.iterations = mode, iterations
        self.cache, self.inflight, self.lock = {}, {}, threading.Lock()
        self.full = self.hits = self.verify_attempts = self.verify_hit_attempts = self.verify_passes = 0
        self.verify_failures = self.verify_cpu_ns = 0

    def evaluate(self, seed):
        if self.mode == "CONTROL":
            value = work(seed, self.iterations)
            with self.lock: self.full += 1
            return output(seed, value)
        key, owner, cached = sha(descriptor(seed, self.iterations)), False, None
        with self.lock:
            if key in self.cache:
                cached = self.cache[key]
            elif key in self.inflight:
                event = self.inflight[key]
            else:
                event, owner = threading.Event(), True
                self.inflight[key] = event
        if owner:
            try:
                value = work(seed, self.iterations)
                stored = make_record(seed, self.iterations, value) if self.mode == "EDEN" else value
                with self.lock:
                    self.cache[key], self.full = stored, self.full + 1
            finally:
                with self.lock: self.inflight.pop(key).set()
        elif cached is None:
            event.wait()
            with self.lock: cached = self.cache[key]
        if owner:
            with self.lock: stored = self.cache[key]
        else:
            stored = cached
            with self.lock: self.hits += 1
        if self.mode == "EDEN":
            # Per-thread CPU avoids double-counting unrelated concurrent
            # request threads inside an individual verification interval.
            started = time.thread_time_ns()
            valid = verify_record(stored, seed, self.iterations)
            elapsed = time.thread_time_ns() - started
            with self.lock:
                self.verify_attempts += 1
                self.verify_hit_attempts += int(not owner)
                self.verify_cpu_ns += elapsed
                self.verify_passes += int(valid)
                self.verify_failures += int(not valid)
            if not valid: raise RuntimeError("verified-reuse record failed integrity verification")
            value = int(stored["value"])
        else:
            value = int(stored)
        return output(seed, value)

def handler_for(state):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path != "/process": self.send_error(404); return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length))
                body = canonical(state.evaluate(int(payload["seed"])))
                self.send_response(200)
            except Exception as exc:
                body = canonical({"error": type(exc).__name__, "message": str(exc)})
                self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)
        def log_message(self, *_args): pass
    return Handler

def post(port, ordinal, seed):
    request = canonical({"seed": seed}); started = time.perf_counter_ns()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    try:
        connection.request("POST", "/process", request, {"Content-Type": "application/json"})
        response = connection.getresponse(); body = response.read()
    finally: connection.close()
    latency = (time.perf_counter_ns() - started) / 1e9
    if response.status != 200: raise RuntimeError(body.decode(errors="replace"))
    return ordinal, json.loads(body), latency, len(request), len(body)

def run_arm(mode, stream, iterations, concurrency):
    state = State(mode, iterations)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(state))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    started_utc, cpu0, wall0 = utc(), time.process_time_ns(), time.perf_counter_ns()
    rows = []
    try:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(post, server.server_address[1], i, seed)
                       for i, seed in enumerate(stream)]
            for future in as_completed(futures): rows.append(future.result())
        # Stop the measurement window when the final HTTP response is consumed.
        # ThreadingHTTPServer.shutdown() can wait for its polling interval and
        # would otherwise add a fixed teardown delay to every arm.
        wall = (time.perf_counter_ns() - wall0) / 1e9
        cpu = (time.process_time_ns() - cpu0) / 1e9
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    rows.sort(key=lambda row: row[0]); latencies = [row[2] for row in rows]
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss_kb = int(rss if platform.system() != "Darwin" else rss / 1024)
    return {
        "mode": mode, "started_utc": started_utc, "completed_utc": utc(),
        "measurement_scope": "fresh child process containing HTTP server and load generator",
        "cpu_seconds": cpu, "wall_seconds": wall,
        "cpu_utilization_equivalent_pct": cpu / wall * 100,
        "max_rss_kb": rss_kb, "max_rss_scope": "child-process lifetime high-water mark",
        "successful_requests": len(rows), "failed_requests": 0,
        "full_executions": state.full, "reuse_hits": state.hits,
        "executions_avoided_vs_control": len(rows) - state.full,
        "verification_attempts": state.verify_attempts,
        "verification_hit_attempts": state.verify_hit_attempts,
        "verification_passes": state.verify_passes,
        "verification_failures": state.verify_failures,
        "verification_thread_cpu_seconds": state.verify_cpu_ns / 1e9,
        "latency_ms": {
            "p50": statistics.median(latencies) * 1000,
            "p95": percentile(latencies, .95) * 1000,
            "p99": percentile(latencies, .99) * 1000,
            "max": max(latencies) * 1000,
        },
        "throughput_requests_per_second": len(rows) / wall,
        "successful_outputs_per_vm_hour": len(rows) / wall * 3600,
        "application_payload_bytes": {
            "request_bodies": sum(row[3] for row in rows),
            "response_bodies": sum(row[4] for row in rows),
            "total": sum(row[3] + row[4] for row in rows),
        },
        "semantic_output_commitment": sha([row[1] for row in rows]),
    }

def child_entry(pipe, mode, stream, iterations, concurrency):
    try: pipe.send({"ok": True, "result": run_arm(mode, stream, iterations, concurrency)})
    except BaseException as exc: pipe.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    finally: pipe.close()

def isolated_arm(mode, stream, iterations, concurrency):
    parent, child = multiprocessing.Pipe(duplex=False)
    process = multiprocessing.get_context("spawn").Process(
        target=child_entry, args=(child, mode, stream, iterations, concurrency))
    process.start(); child.close(); message = parent.recv(); parent.close(); process.join()
    if process.exitcode != 0 or not message["ok"]:
        raise RuntimeError(f"{mode} arm failed (exit {process.exitcode}): {message.get('error')}")
    return message["result"]

def delta(baseline, candidate, reduction=False):
    return ((1 - candidate / baseline) if reduction else (candidate / baseline - 1)) * 100 if baseline else None

def compare(arms):
    control, cache, eden = arms["CONTROL"], arms["CACHE"], arms["EDEN"]
    result = {
        "output_equivalence": len({x["semantic_output_commitment"] for x in arms.values()}) == 1,
        "execution_accounting_valid": all(
            x["full_executions"] + x["executions_avoided_vs_control"] == x["successful_requests"]
            for x in arms.values()),
    }
    for label, candidate in (("cache_vs_control", cache), ("eden_vs_control", eden)):
        result[label] = {
            "cpu_reduction_pct": delta(control["cpu_seconds"], candidate["cpu_seconds"], True),
            "wall_reduction_pct": delta(control["wall_seconds"], candidate["wall_seconds"], True),
            "throughput_gain_pct": delta(control["throughput_requests_per_second"], candidate["throughput_requests_per_second"]),
            "p95_latency_reduction_pct": delta(control["latency_ms"]["p95"], candidate["latency_ms"]["p95"], True),
            "max_rss_reduction_pct": delta(control["max_rss_kb"], candidate["max_rss_kb"], True),
        }
    result["eden_vs_cache"] = {
        "cpu_overhead_pct": delta(cache["cpu_seconds"], eden["cpu_seconds"]),
        "wall_overhead_pct": delta(cache["wall_seconds"], eden["wall_seconds"]),
        "throughput_delta_pct": delta(cache["throughput_requests_per_second"], eden["throughput_requests_per_second"]),
        "p95_latency_delta_pct": delta(cache["latency_ms"]["p95"], eden["latency_ms"]["p95"]),
    }
    return result

def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2], text=True,
            stderr=subprocess.DEVNULL, timeout=5).strip()
    except Exception: return None

def host_metadata(label):
    path = Path("/sys/class/dmi/id/sys_vendor")
    vendor = path.read_text().strip() if path.exists() else None
    azure = bool(vendor and "microsoft" in vendor.lower())
    return {
        "environment_label": label, "environment_label_source": "USER_SUPPLIED_NOT_VERIFIED",
        "azure_hardware_signal": azure,
        "azure_hardware_signal_basis": "DMI sys_vendor contains Microsoft" if azure else "not detected",
        "hostname": platform.node(), "platform": platform.platform(),
        "python": platform.python_version(), "logical_cpu_count": os.cpu_count(),
        "git_commit": git_commit(),
    }

def parse_order(value, seed):
    order = [x.strip().upper() for x in value.split(",")] if value else list(MODES)
    if not value: random.Random(seed).shuffle(order)
    if sorted(order) != sorted(MODES): raise ValueError("arm order must contain CONTROL,CACHE,EDEN once")
    return order

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=3000)
    parser.add_argument("--iterations", type=int, default=30000)
    parser.add_argument("--reuse", type=float, default=.5)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--seed", type=int, default=260907)
    parser.add_argument("--arm-order")
    parser.add_argument("--environment", default="UNSPECIFIED_HOST")
    parser.add_argument("--vm-hour-cost", type=float)
    parser.add_argument("--external-evidence")
    parser.add_argument("--output-dir", default="experiments/eden-azure-application-001/results")
    args = parser.parse_args(argv)
    if not 0 <= args.reuse < 1 or min(args.requests, args.iterations, args.concurrency) < 1:
        parser.error("invalid numeric arguments")
    if args.vm_hour_cost is not None and args.vm_hour_cost < 0: parser.error("negative VM price")
    try: order = parse_order(args.arm_order, args.seed)
    except ValueError as exc: parser.error(str(exc))
    run_id = str(uuid.uuid4()); stream = request_stream(args.requests, args.reuse, args.seed)
    unique = len(set(stream)); request_commitment = sha({"stream": stream, "iterations": args.iterations})
    print("=" * 78, "\n EDEN AZURE HTTP APPLICATION BENCHMARK\n", EXP, "\n", "=" * 78, sep="")
    print(f"Run ID: {run_id}\nRequests/arm: {args.requests:,}\nRealized reuse: {1-unique/len(stream):.2%}")
    print(f"Arm order: {' -> '.join(order)}\nRequest commitment: {request_commitment}")
    arms = {}
    for mode in order:
        print(f"\nRunning isolated {mode} arm...", flush=True)
        arms[mode] = isolated_arm(mode, stream, args.iterations, args.concurrency)
        x = arms[mode]
        print(f"{mode}: CPU {x['cpu_seconds']:.3f}s | wall {x['wall_seconds']:.3f}s | p95 {x['latency_ms']['p95']:.2f}ms | {x['throughput_requests_per_second']:.2f} req/s")
    comparison = compare(arms); host = host_metadata(args.environment)
    external = None
    if args.external_evidence:
        path = Path(args.external_evidence); raw = path.read_bytes()
        external = {"path_as_supplied": str(path), "sha256": sha_bytes(raw), "bytes": len(raw),
                    "interpretation_status": "ATTACHED_NOT_INTERPRETED_OR_TIME_ALIGNED"}
    economics = {"status": "NOT_CALCULATED"}
    if args.vm_hour_cost is not None:
        economics = {"status": "MODELLED_FROM_USER_SUPPLIED_VM_HOUR_PRICE",
          "vm_hour_cost": args.vm_hour_cost, "arms": {
            mode: {"modelled_cost_per_million_successful_outputs":
                   args.vm_hour_cost * 1_000_000 / x["successful_outputs_per_vm_hour"]}
            for mode, x in arms.items()}}
    report = {
      "schema": "eden.azure.application.v2", "experiment": EXP, "run_id": run_id,
      "created_utc": utc(), "evidence_class": "MEASURED_AZURE_VM_LOCAL_HTTP_HARNESS"
        if host["azure_hardware_signal"] else "MEASURED_LOCAL_HTTP_HARNESS",
      "attestation": "SELF_REPORTED_UNATTESTED", "independent_validation": "NOT_PERFORMED",
      "host": host, "configuration": {
        "requests_per_arm": args.requests, "iterations_per_full_execution": args.iterations,
        "requested_reuse_fraction": args.reuse, "realized_reuse_fraction": 1-unique/len(stream),
        "unique_requests": unique, "concurrency": args.concurrency, "seed": args.seed,
        "arm_order": order, "arm_runs_per_mode": 1},
      "request_commitment": request_commitment,
      "verified_reuse_policy": {"document": POLICY, "commitment": sha(POLICY)},
      "arms": arms, "comparison": comparison, "economics": economics,
      "external_evidence": external,
      "truth_boundary": {
        "measured": [
          "whole child-process CPU time for load generator plus local HTTP service",
          "child-process wall time and lifetime peak RSS",
          "client-observed loopback latency and successful-request throughput",
          "application request/response body bytes; HTTP and TCP overhead excluded",
          "full executions, exact reuse hits, executions avoided, output equivalence and verification outcomes"],
        "implemented_not_independently_proven": [
          "SHA-256 commitments detect modification of the bound record under the stated policy",
          "single-flight accounting prevents concurrent duplicate execution for an identical key"],
        "not_claimed": [
          "production workload representativeness", "server-only CPU or RSS",
          "network performance beyond host loopback", "Azure platform or hypervisor CPU reduction",
          "datacentre energy or carbon reduction", "actual Azure invoice savings",
          "statistical significance or confidence intervals from one run per arm",
          "resistance to arm-order drift", "security against a compromised runtime",
          "independent replication or third-party validation"]}}
    report["report_commitment"] = sha(report)
    directory = Path(args.output_dir); directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{EXP}-{run_id[:8]}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("\n" + "="*78 + "\n RESULTS\n" + "="*78)
    print("OUTPUT EQUIVALENCE:", "PASS" if comparison["output_equivalence"] else "FAIL")
    print(f"EDEN EXECUTIONS AVOIDED: {arms['EDEN']['executions_avoided_vs_control']:,}")
    print(f"EDEN CPU REDUCTION vs CONTROL: {comparison['eden_vs_control']['cpu_reduction_pct']:.2f}%")
    print(f"EDEN THROUGHPUT GAIN vs CONTROL: {comparison['eden_vs_control']['throughput_gain_pct']:.2f}%")
    print(f"EDEN CPU OVERHEAD vs CACHE: {comparison['eden_vs_cache']['cpu_overhead_pct']:+.2f}%")
    print("REPORT COMMITMENT:", report["report_commitment"]); print("SAVED:", path)
    return 0 if comparison["output_equivalence"] and arms["EDEN"]["verification_failures"] == 0 else 1

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
