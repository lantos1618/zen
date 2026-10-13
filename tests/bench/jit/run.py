#!/usr/bin/env python3
"""Interpreter (--backend jit) against the compiled backends.

For each workload and backend:
  front  the compiler's frontend and lowering: `zen build --backend X` to a
         file, median of --reps. The jit's front is measured, not proxied:
         its fitted intercept, i.e. process start, frontend, lowering,
         decoding and setup together;
  tool   the external toolchain (cc -O0/-O2, as+ld), median of --reps;
  slope  time per unit of work (one round): a least-squares fit of the
         median wall time over four sizes, with R^2 and a 95% confidence
         interval (Student t), free of startup and setup. Every size of every
         backend is run once to warm up; then --reps rounds each time every
         backend at every size, the backend order rotating each round, so
         drift and thermal state are spread over all backends alike.
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
    ("map",      "tests/bench/jit/map",         (16, 48, 80, 128), (4, 8, 12, 16), "round"),
]
PYTHON_REFS = {"sha256": (os.path.join(HERE, "ref_sha256.py"), (1, 2, 3, 4)),
               "fib24": (os.path.join(HERE, "ref_fib.py"), (8, 24, 40, 64)),
               "map": (os.path.join(HERE, "ref_map.py"), (8, 24, 40, 64))}
# Two-sided 95% Student t by degrees of freedom.
T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306}

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

def run_checked(run, reference, size, label):
    dt, p = timed(run)
    if p.returncode != 0:
        raise RuntimeError(f"{' '.join(run)} exited {p.returncode}: {p.stdout[-300:]}{p.stderr[-300:]}")
    want = reference.setdefault(size, p.stdout)
    if p.stdout != want:
        raise Mismatch(f"{label} at size {size}: {p.stdout.strip()!r} != {want.strip()!r}")
    return dt

def measure(runners, reps, pin):
    """Times every runner (label, argv, sizes, reference) round-robin: one
    checked warm-up per size, then `reps` rounds in a rotating order."""
    times = {label: {size: [] for size in sizes} for label, _, sizes, _ in runners}
    for label, argv, sizes, reference in runners:
        for size in sizes:
            run_checked(pin + argv + [str(size)], reference, size, label)
    for r in range(reps):
        k = r % len(runners)
        for label, argv, sizes, reference in runners[k:] + runners[:k]:
            for size in sizes:
                times[label][size].append(run_checked(pin + argv + [str(size)], reference, size, label))
    return {label: fit([{"size": size, "median": statistics.median(ts), "min": min(ts), "max": max(ts)}
                        for size, ts in by.items()]) for label, by in times.items()}

def fit(rows):
    xs = [r["size"] for r in rows]
    ys = [r["median"] for r in rows]
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    df = len(xs) - 2
    ci = T95.get(df, 1.96) * (ss_res / df / sxx) ** 0.5 if df > 0 else float("inf")
    signal = slope * (xs[-1] - xs[0])
    spread = max(r["max"] - r["min"] for r in rows)
    return {"points": rows, "per_unit": slope, "intercept": intercept,
            "ci95": ci, "r2": 1 - ss_res / ss_tot if ss_tot else 1.0,
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
        builds = [("c-O2", "c", ["cc", "-O2"]), ("c-O0", "c", ["cc", "-O0"]), ("asm", "asm", None), ("zen-js", "js", None)]
        try:
            runners, extra = [], {}
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
                argv = ["node", src] if backend == "js" else [exe]
                runners.append((label, argv, sizes, reference))
                extra[label] = {"front": statistics.median(fronts), "tool": statistics.median(tools)}
            # c-O2 fixes the expected output at the jit's sizes too.
            for size in jsizes:
                run_checked(pin + runners[0][1] + [str(size)], reference, size, "c-O2")
            runners.append(("jit", base + ["--backend", "jit", "--"], jsizes, reference))
            if name in PYTHON_REFS:
                script, psizes = PYTHON_REFS[name]
                runners.append(("cpython", ["python3", script], psizes, {}))
            for label, result in measure(runners, args.reps, pin).items():
                result.update(extra.get(label, {"front": result["intercept"] if label == "jit" else 0.0, "tool": 0.0}))
                row["backends"][label] = result
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
    print(f"{'backend':8} {'front s':>8} {'tool s':>7} {'per unit':>10} {'95% CI':>8} {'R^2':>7} {'noise':>6} {'vs O2':>7} {'vs O0':>7}")
    for label, b in row["backends"].items():
        ratio = lambda ref: f"{b['per_unit'] / ref:.1f}x" if ref else "-"
        flag = " NOISY" if b["noise"] > 0.10 else ""
        print(f"{label:8} {b['front']:8.2f} {b['tool']:7.2f} {b['per_unit'] * 1000:10.2f} {'±%.1f%%' % (100 * b['ci95'] / b['per_unit']):>8} {b['r2']:7.4f} "
              f"{b['noise'] * 100:5.1f}% {ratio(o2):>7} {ratio(o0):>7}{flag}")

if __name__ == "__main__":
    main()
