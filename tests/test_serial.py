"""Unit tests for serial.py's chardev_args and SerialConsole. No QEMU needed -
SerialConsole is tested against a plain local TCP socket standing in for
QEMU's socket chardev.
"""

import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp.serial import SerialConsole, chardev_args  # noqa: E402


def test_chardev_args_wires_host_port_and_logfile():
    args = chardev_args("/tmp/serial.log", 12345)
    assert args == [
        "-chardev",
        "socket,id=serial0,host=127.0.0.1,port=12345,"
        "server=on,wait=off,logfile=/tmp/serial.log,logappend=on",
        "-serial",
        "chardev:serial0",
    ]


def _listen():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    return server, server.getsockname()[1]


def test_send_connects_once_and_writes_bytes():
    server, port = _listen()
    try:
        console = SerialConsole(port)
        console.send("hello\n")
        conn, _ = server.accept()
        try:
            assert conn.recv(1024) == b"hello\n"
        finally:
            conn.close()
    finally:
        console.close()
        server.close()


def test_send_reuses_the_same_connection():
    server, port = _listen()
    try:
        console = SerialConsole(port)
        console.send("a")
        conn, _ = server.accept()
        assert console._sock is not None
        first_sock = console._sock
        console.send("b")
        assert console._sock is first_sock
        assert conn.recv(1024) == b"ab"
        conn.close()
    finally:
        console.close()
        server.close()


class _FakeSocket:
    def __init__(self, fail):
        self.fail = fail
        self.sent = b""

    def sendall(self, data):
        if self.fail:
            raise OSError("Broken pipe")
        self.sent += data

    def close(self):
        pass


def test_send_reconnects_after_the_peer_drops_the_connection(monkeypatch):
    sockets = [_FakeSocket(fail=True), _FakeSocket(fail=False)]
    made = []

    def fake_create_connection(addr, timeout=None):
        made.append(addr)
        return sockets[len(made) - 1]

    monkeypatch.setattr(
        "qemu_mcp.serial.socket.create_connection", fake_create_connection
    )

    console = SerialConsole(9999)
    console.send("first")  # sockets[0].sendall raises -> reconnects to sockets[1]
    console.send("second")  # reuses sockets[1], no further reconnect

    assert made == [("127.0.0.1", 9999), ("127.0.0.1", 9999)]
    assert sockets[1].sent == b"firstsecond"


def test_close_is_safe_to_call_twice_and_before_any_send():
    console = SerialConsole(0)
    console.close()
    console.close()
