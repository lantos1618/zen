#!/usr/bin/env python3
"""Compile real std.net users and test-only ABI probes against the host SDK."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import threading

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
p = argparse.ArgumentParser()
p.add_argument('--zen', type=Path, required=True)
p.add_argument('--std', type=Path, default=ROOT / 'src')
p.add_argument('--ubsan', action='store_true')
args = p.parse_args()

def read(conn, count):
    out = b''
    while len(out) < count:
        part = conn.recv(count-len(out))
        if not part:
            break
        out += part
    return out

class Peer:
    def __init__(self, family, host):
        self.listener = socket.socket(family, socket.SOCK_STREAM)
        self.listener.bind((host, 0))
        self.listener.listen(3)
        self.listener.settimeout(20)
        self.port = self.listener.getsockname()[1]
        self.error = None
    def serve(self):
        try:
            conn, _ = self.listener.accept()
            with conn:
                conn.settimeout(10)
                assert read(conn, 4) == b'ping'
                conn.sendall(b'p')
                assert read(conn, 3) == b'ack'
                conn.sendall(b'ong')
                assert conn.recv(1) == b''
            conn, _ = self.listener.accept()
            with conn:
                conn.settimeout(10)
                assert conn.recv(1) == b'', 'scope drop did not close socket'
            conn, _ = self.listener.accept()
            with conn:
                conn.settimeout(10)
                assert read(conn, 4) == b'pipe'
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 0))
        except BaseException as exc:
            self.error = exc
        finally:
            self.listener.close()
    def start(self):
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()
    def finish(self):
        self.thread.join(22)
        assert not self.thread.is_alive(), 'peer did not finish'
        if self.error:
            raise self.error

with tempfile.TemporaryDirectory(prefix='zen-native-socket-') as folder:
    work = Path(folder)
    shutil.copy(HERE / 'probe.h', work)
    env = dict(os.environ, ZEN_STD=str(args.std.resolve()))
    def build(name, substitutions=()):
        source = (HERE / (name + '.zen')).read_text()
        for old, new in substitutions:
            assert old in source, (name, old)
            source = source.replace(old, new)
        (work / 'main.zen').write_text(source)
        subprocess.run([str(args.zen.resolve()), 'build', str(work), '--emit-c', '-o', str(work / 'generated.c')], env=env, check=True, timeout=120)
        binary = work / name
        flags = ['-fsanitize=undefined', '-fno-sanitize-recover=all'] if args.ubsan else []
        subprocess.run(['clang', '-O1', '-g', '-Wno-parentheses-equality', *flags, '-I', str(work), '-include', str(work / 'probe.h'), str(work / 'generated.c'), '-o', str(binary)], check=True, timeout=90)
        return binary
    def execute(binary):
        # subprocess restores Python-ignored SIGPIPE; Zen also explicitly resets it.
        try:
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired as exc:
            print(exc.stdout, exc.stderr, flush=True)
            raise
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        print(result.stdout, end='')
    execute(build('record'))
    for family, host in [(socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')]:
        # Darwin silently drops SYNs for bound non-listening sockets. Release
        # an ephemeral port instead; concurrent reuse causes a failing test.
        with socket.socket(family, socket.SOCK_STREAM) as refused:
            refused.bind((host, 0))
            refusal_port = refused.getsockname()[1]
        peer = Peer(family, host)
        replacements = [('HARNESS_HOST', host), ('REFUSED_PORT: u16 = 0', f'REFUSED_PORT: u16 = {refusal_port}')]
        binary = build('socket', replacements + [('PORT: u16 = 0', f'PORT: u16 = {peer.port}')])
        peer.start()
        try:
            execute(binary)
        except BaseException:
            peer.listener.close()
            peer.thread.join(1)
            raise
        else:
            peer.finish()
        execute(build('failure', replacements))
        print(f'PASS family {host}')
