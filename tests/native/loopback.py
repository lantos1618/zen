#!/usr/bin/env python3
"""Run one jit corpus program against tests/run.py's loopback peer.

usage: loopback.py tcp|tls <work> <staged entry> -- <program> [args...]

As tests/run.py does for corpus/net/tcp_connect and corpus/net/tls_connect:
bind the peer, rewrite the staged entry's one `HARNESS_PORT` line to its port,
export SSL_CERT_FILE for TLS, then run the program. The jit compiles the
staged root as the program starts, so the rewrite lands before compilation.
A peer that could not be staged, or that saw the wrong exchange, is an
`error:` line on stdout and a nonzero exit, never a silent pass.
"""
import os
import re
import ssl
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run  # noqa: E402

TIMEOUT = 600.0


def fail(message: str) -> int:
    print(f"error: {message}", flush=True)
    print(f"loopback.py: {message}", file=sys.stderr)
    return 1


def main() -> int:
    kind, work, entry = sys.argv[1:4]
    if kind not in ("tcp", "tls") or sys.argv[4] != "--":
        print(__doc__, file=sys.stderr)
        return 2
    command = sys.argv[5:]
    peer = None
    try:
        peer = (run.LoopbackPeer() if kind == "tcp"
                else run.TlsLoopbackPeer(Path(work), TIMEOUT))
        path = Path(entry)
        patched, n = re.subn(
            r"HARNESS_PORT\* : u16 = \d+",
            f"HARNESS_PORT* : u16 = {peer.port}",
            path.read_text(encoding="utf-8"),
        )
        if n != 1:
            raise AssertionError(f"HARNESS_PORT lines rewritten: {n}, want 1")
        path.write_text(patched, encoding="utf-8")
    except (run.HarnessError, OSError, AssertionError, ssl.SSLError) as e:
        if peer is not None:
            peer.close()
        return fail(f"the harness could not stage loopback {kind.upper()}: {e}")
    env = dict(os.environ)
    if isinstance(peer, run.TlsLoopbackPeer):
        env["SSL_CERT_FILE"] = str(peer.cert)
    peer.start(TIMEOUT)
    code = subprocess.run(command, env=env).returncode
    sys.stdout.flush()
    problem = peer.finish(TIMEOUT)
    if problem:
        fail(f"loopback peer failed: {problem}")
        return code if code != 0 else 1
    return code


if __name__ == "__main__":
    sys.exit(main())
