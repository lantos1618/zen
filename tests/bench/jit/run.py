#!/usr/bin/env python3
"""Interpreter (--backend jit) against the compiled backends.

For each workload and backend it measures, separately:
  front  the compiler's frontend + lowering (`zen build` to source, or the
         jit's own run at zero work);
  tool   the external toolchain (cc -O0/-O2, as+ld);
  run    the program at two sizes; the slope gives time per unit of work
         (one round), free of startup and setup.
Every timing is the median of --reps runs, with min/max kept. The program's
output must be identical across backends at the same size, or the row is
marked MISMATCH. Results go to build/bench-jit/results.json and a table.
"""
import argparse, json, os, shutil, statistics, subprocess, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# name, root, sizes for compiled backends, sizes for the jit, unit
WORKLOADS = [
    ("sha256",   "tests/native/bench/sha256",   (8, 64),  (1, 3),  "MiB"),
    ("blake2b",  "tests/native/bench/blake2b",  (8, 64),  (1, 3),  "MiB"),
    ("chacha20", "tests/native/bench/chacha20", (8, 64),  (1, 3),  "MiB"),
    ("fib24",    "tests/bench/jit/fib",         (16, 128), (1, 3), "fib(24)"),
]

def timed(argv, cwd=None, env=None):
    t = time.perf_counter()
    p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    return time.perf_counter() - t, p

def median_run(argv, reps, env=None):
    times, out = [], None
    for _ in range(reps):
        dt, p = timed(argv, env=env)
        if p.returncode != 0:
            raise RuntimeError(f"{' '.join(argv)} exited {p.returncode}: {p.stdout[-300:]}{p.stderr[-300:]}")
        times.append(dt)
        out = p.stdout
    return {"median": statistics.median(times), "min": min(times), "max": max(times)}, out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zen", default="./zen")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--jit-reps", type=int, default=3)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    os.chdir(REPO)
    zen = os.path.abspath(args.zen)
    work = os.path.join(REPO, "build/bench-jit")
    os.makedirs(work, exist_ok=True)
    node = shutil.which("node")
    results = []
    for name, root, sizes, jsizes, unit in WORKLOADS:
        if args.only and name not in args.only.split(","):
            continue
        row = {"name": name, "unit": unit, "backends": {}}
        outs = {}
        base = [zen, "build", root, "--entry", "main.zen", "--std", "src"]
        # Compiled backends.
        builds = {
            "c-O0": ("c", ["cc", "-O0"]), "c-O2": ("c", ["cc", "-O2"]),
            "asm": ("asm", None), "js": ("js", None),
        }
        for label, (backend, cc) in builds.items():
            if backend == "js" and not node:
                continue
            ext = {"c": "c", "asm": "s", "js": "js"}[backend]
            src = os.path.join(work, f"{name}.{label}.{ext}")
            exe = os.path.join(work, f"{name}.{label}")
            front, p = timed(base + ["--backend", backend, "-o", src])
            if p.returncode != 0:
                row["backends"][label] = {"error": (p.stdout + p.stderr).strip().splitlines()[0]}
                continue
            tool = 0.0
            if cc:
                tool, p = timed(cc + [src, "-lm", "-o", exe])
            elif backend == "asm":
                t1, p = timed(["as", src, "-o", exe + ".o"])
                t2, p2 = timed(["ld", "-static", exe + ".o", "-o", exe])
                tool = t1 + t2
            argv = (["node", src] if backend == "js" else [exe])
            small, out_small = median_run(argv + [str(sizes[0])], args.reps)
            large, _ = median_run(argv + [str(sizes[1])], args.reps)
            check, out_check = median_run(argv + [str(jsizes[1])], 1)
            outs[label] = out_check
            per = (large["median"] - small["median"]) / (sizes[1] - sizes[0])
            row["backends"][label] = {"front": front, "tool": tool, "small": small, "large": large,
                                      "sizes": sizes, "per_unit": per}
        # The interpreter: front-end cost is its run at zero work.
        jit = base + ["--backend", "jit", "--"]
        zero, _ = median_run(jit + ["0"], args.jit_reps)
        small, _ = median_run(jit + [str(jsizes[0])], args.jit_reps)
        large, out_large = median_run(jit + [str(jsizes[1])], args.jit_reps)
        outs["jit"] = out_large
        per = (large["median"] - small["median"]) / (jsizes[1] - jsizes[0])
        row["backends"]["jit"] = {"front": zero["median"], "small": small, "large": large,
                                  "sizes": jsizes, "per_unit": per}
        ref = outs.get("c-O2")
        row["outputs_match"] = all(o == ref for o in outs.values())
        row["outputs"] = outs
        results.append(row)
        print_row(row)
    with open(os.path.join(work, "results.json"), "w") as f:
        json.dump(results, f, indent=1)

def print_row(row):
    print(f"\n== {row['name']} (per {row['unit']}) outputs {'match' if row['outputs_match'] else 'MISMATCH'}")
    o2 = row["backends"].get("c-O2", {}).get("per_unit")
    print(f"{'backend':8} {'front s':>8} {'tool s':>8} {'per unit ms':>12} {'vs c-O2':>8}")
    for label, b in row["backends"].items():
        if "error" in b:
            print(f"{label:8} refused: {b['error']}")
            continue
        ratio = f"{b['per_unit'] / o2:.1f}x" if o2 else "-"
        print(f"{label:8} {b['front']:8.2f} {b.get('tool', 0):8.2f} {b['per_unit'] * 1000:12.2f} {ratio:>8}")

if __name__ == "__main__":
    main()
