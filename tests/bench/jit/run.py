#!/usr/bin/env python3
"""Interpreter (--backend jit) against the compiled backends.

For each workload and backend:
  front  the compiler's frontend and lowering: `zen build --backend c` to a
         file (the jit runs the same lowering, so this is its frontend too);
  tool   the external toolchain (cc -O0/-O2, as+ld), median of --reps;
  slope  time per unit of work (one round): a least-squares fit of the
         median wall time over four sizes, with R^2, free of startup and
         setup. Each size is run once to warm up, then --reps times.
Every timed run's stdout must equal the reference for that size (c-O2's),
or the row is marked MISMATCH. Runs are pinned to one CPU with taskset when
available. Rows whose spread (max-min over all sizes, as a share of the
fitted signal) exceeds 10% are flagged NOISY. Reference rows run the same
algorithm in CPython. Results and the machine, compilers and revision go to
build/bench-jit/results.json.
"""
import argparse, json, os, platform, shutil, statistics, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

# name, root, sizes for compiled backends, sizes for the jit, unit
WORKLOADS = [
    ("sha256",   "tests/native/bench/sha256",   (8, 24, 40, 64), (1, 2, 3, 4),    "MiB"),
    ("blake2b",  "tests/native/bench/blake2b",  (8, 24, 40, 64), (1, 2, 3, 4),    "MiB"),
    ("chacha20", "tests/native/bench/chacha20", (8, 24, 40, 64), (1, 2, 3, 4),    "MiB"),
    ("fib24",    "tests/bench/jit/fib",         (64, 192, 320, 512), (8, 24, 40, 64), "fib(24)"),
]
PYTHON_REFS = {"sha256": (os.path.join(HERE, "ref_sha256.py"), (1, 2, 3, 4)),
               "fib24": (os.path.join(HERE, "ref_fib.py"), (4, 8, 12, 16))}

def capture(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout.strip().splitlines()[0]
    except (OSError, IndexError):
        return "unavailable"

def timed(argv):
    t = time.perf_counter()
    p = subprocess.run(argv, capture_output=True, text=True)
    return time.perf_counter() - t, p

class Mismatch(Exception):
    pass

def measure(argv, sizes, reps, pin, reference, label):
    """Median, min and max wall time per size; checks every run's stdout."""
    rows = []
    for size in sizes:
        run = pin + argv + [str(size)]
        timed(run)  # warm-up, discarded
        times = []
        for _ in range(reps):
            dt, p = timed(run)
            if p.returncode != 0:
                raise RuntimeError(f"{' '.join(run)} exited {p.returncode}: {p.stdout[-300:]}{p.stderr[-300:]}")
            want = reference.setdefault(size, p.stdout)
            if p.stdout != want:
                raise Mismatch(f"{label} at size {size}: {p.stdout.strip()!r} != {want.strip()!r}")
            times.append(dt)
        rows.append({"size": size, "median": statistics.median(times), "min": min(times), "max": max(times)})
    return fit(rows)

def fit(rows):
    xs = [r["size"] for r in rows]
    ys = [r["median"] for r in rows]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    signal = slope * (xs[-1] - xs[0])
    spread = max(r["max"] - r["min"] for r in rows)
    return {"points": rows, "per_unit": slope, "intercept": intercept,
            "r2": 1 - ss_res / ss_tot if ss_tot else 1.0,
            "noise": spread / signal if signal > 0 else float("inf")}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zen", default="./zen")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--only", default="")
    ap.add_argument("--cpu", default="2", help="CPU to pin runs to ('' to disable)")
    args = ap.parse_args()
    os.chdir(REPO)
    zen = os.path.abspath(args.zen)
    work = os.path.join(REPO, "build/bench-jit")
    os.makedirs(work, exist_ok=True)
    node = shutil.which("node")
    pin = ["taskset", "-c", args.cpu] if args.cpu and shutil.which("taskset") else []
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor()) \
        if os.path.exists("/proc/cpuinfo") else platform.processor()
    machine = {"cpu": cpu, "cc": capture(["cc", "--version"]), "node": capture(["node", "--version"]) if node else "absent",
               "python": platform.python_version(), "revision": capture(["git", "rev-parse", "HEAD"]),
               "pinned": " ".join(pin) or "no", "reps": args.reps}
    for k, v in machine.items():
        print(f"# {k}: {v}")
    results = {"machine": machine, "workloads": []}
    for name, root, sizes, jsizes, unit in WORKLOADS:
        if args.only and name not in args.only.split(","):
            continue
        row = {"name": name, "unit": unit, "backends": {}, "mismatch": None}
        reference = {}
        base = [zen, "build", root, "--entry", "main.zen", "--std", "src"]
        builds = [("c-O2", "c", ["cc", "-O2"]), ("c-O0", "c", ["cc", "-O0"]), ("asm", "asm", None), ("js", "js", None)]
        front = []
        try:
            for label, backend, cc in builds:
                if backend == "js" and not node:
                    continue
                ext = {"c": "c", "asm": "s", "js": "js"}[backend]
                src = os.path.join(work, f"{name}.{label}.{ext}")
                exe = os.path.join(work, f"{name}.{label}")
                fronts, tools = [], []
                for _ in range(args.reps):
                    dt, p = timed(base + ["--backend", backend, "-o", src])
                    if p.returncode != 0:
                        raise RuntimeError((p.stdout + p.stderr).strip().splitlines()[0])
                    fronts.append(dt)
                    if cc:
                        dt, p = timed(cc + [src, "-lm", "-o", exe])
                    elif backend == "asm":
                        t1, _ = timed(["as", src, "-o", exe + ".o"])
                        t2, _ = timed(["ld", "-static", exe + ".o", "-o", exe])
                        dt = t1 + t2
                    else:
                        dt = 0.0
                    tools.append(dt)
                if backend == "c":
                    front += fronts
                argv = ["node", src] if backend == "js" else [exe]
                result = measure(argv, sizes, args.reps, pin, reference, label)
                for size in jsizes:
                    if size not in reference:
                        measure(argv, [size, size + 1], 1, pin, reference, label)
                result.update(front=statistics.median(fronts), tool=statistics.median(tools))
                row["backends"][label] = result
            result = measure(base + ["--backend", "jit", "--"], jsizes, args.reps, pin, reference, "jit")
            result.update(front=statistics.median(front), tool=0.0)
            row["backends"]["jit"] = result
            if name in PYTHON_REFS:
                script, psizes = PYTHON_REFS[name]
                result = measure(["python3", script], psizes, args.reps, pin, {}, "cpython")
                result.update(front=0.0, tool=0.0)
                row["backends"]["cpython"] = result
        except Mismatch as e:
            row["mismatch"] = str(e)
        results["workloads"].append(row)
        print_row(row)
    with open(os.path.join(work, "results.json"), "w") as f:
        json.dump(results, f, indent=1)

def print_row(row):
    print(f"\n== {row['name']} (ms per {row['unit']}) outputs {'MISMATCH: ' + row['mismatch'] if row['mismatch'] else 'match'}")
    o2 = row["backends"].get("c-O2", {}).get("per_unit")
    o0 = row["backends"].get("c-O0", {}).get("per_unit")
    print(f"{'backend':8} {'front s':>8} {'tool s':>7} {'per unit':>10} {'R^2':>7} {'noise':>6} {'vs O2':>7} {'vs O0':>7}")
    for label, b in row["backends"].items():
        ratio = lambda ref: f"{b['per_unit'] / ref:.1f}x" if ref else "-"
        flag = " NOISY" if b["noise"] > 0.10 else ""
        print(f"{label:8} {b['front']:8.2f} {b['tool']:7.2f} {b['per_unit'] * 1000:10.2f} {b['r2']:7.4f} "
              f"{b['noise'] * 100:5.1f}% {ratio(o2):>7} {ratio(o0):>7}{flag}")

if __name__ == "__main__":
    main()
