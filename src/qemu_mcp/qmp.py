"""Minimal synchronous QMP (QEMU Machine Protocol) client.

QMP is a JSON-line protocol over a socket. QEMU sends a greeting on
connect, requires a `qmp_capabilities` handshake before accepting
commands, and interleaves async events with command responses - so the
response loop must skip anything carrying an "event" key.
"""

from __future__ import annotations

import json
import socket
import time


class QMPError(RuntimeError):
    pass


class QMPClient:
    def __init__(self, port: int, connect_timeout: float = 20.0):
        # First launch of QEMU on a cold machine can take a long time
        # (AV scanning), so retry-connect instead of one-shot.
        deadline = time.monotonic() + connect_timeout
        last_err: OSError | None = None
        self.sock: socket.socket | None = None
        while time.monotonic() < deadline:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError as e:
                last_err = e
                time.sleep(0.2)
        if self.sock is None:
            raise QMPError(f"could not connect to QMP on 127.0.0.1:{port}: {last_err}")
        self.sock.settimeout(15)
        self._buf = b""
        self._read_msg()  # greeting
        self.command("qmp_capabilities")

    def _read_msg(self) -> dict:
        while b"\n" not in self._buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise QMPError("QMP connection closed by QEMU")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line)

    def command(self, name: str, **arguments):
        msg: dict = {"execute": name}
        if arguments:
            msg["arguments"] = arguments
        self.sock.sendall(json.dumps(msg).encode() + b"\n")
        while True:
            resp = self._read_msg()
            if "return" in resp:
                return resp["return"]
            if "error" in resp:
                raise QMPError(f"{name}: {resp['error'].get('desc', resp['error'])}")
            # anything else is an async event - skip it

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None
