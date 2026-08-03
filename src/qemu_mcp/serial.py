"""Bidirectional serial console: chardev args + a persistent-socket sender.

QEMU's plain `-serial file:path` (the old setup) is write-only from the
guest's side - there's no way to send bytes back in. Swapping to a
TCP-backed socket chardev with `logfile=` keeps the same continuously
readable log while adding a socket an agent can write to, driving the
guest's serial console the same way qemu_type drives the keyboard.
"""

from __future__ import annotations

import socket


def chardev_args(serial_path: str, port: int) -> list[str]:
    """Build the -chardev/-serial args for a logged, TCP-backed serial console.

    server=on,wait=off: QEMU listens on `port` but boots immediately rather
    than blocking for a client to connect. logfile/logappend keep writing
    the guest's output to serial_path exactly as `-serial file:` did, so
    qemu_serial and qemu_wait_serial are unaffected.
    """
    chardev = (
        f"socket,id=serial0,host=127.0.0.1,port={port},"
        f"server=on,wait=off,logfile={serial_path},logappend=on"
    )
    return ["-chardev", chardev, "-serial", "chardev:serial0"]


class SerialConsole:
    """Bidirectional handle to a VM's serial chardev socket at 127.0.0.1:port.

    Connects lazily and holds the connection open for reuse. QEMU's socket
    chardev treats a client disconnect as a hangup on the serial line, which
    can kill a guest login shell - reconnecting on every send would hang up
    the line after every single write.
    """

    def __init__(self, port: int) -> None:
        self.port = port
        self._sock: socket.socket | None = None

    def send(self, data: str) -> None:
        payload = data.encode("utf-8")
        if self._sock is None:
            self._sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            self._sock.sendall(payload)
        except OSError:
            self._sock.close()
            self._sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            self._sock.sendall(payload)

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
