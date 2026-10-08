"""Unit tests for serial.py's chardev_args and SerialConsole. No QEMU needed -
SerialConsole is tested against a plain local TCP socket standing in for
QEMU's socket chardev.
"""

import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402

from qemu_mcp.serial import SerialConsole, SerialError, chardev_args  # noqa: E402


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


class _ConcurrencyDetectingSocket:
    """Stands in for the real serial socket and records whether two threads
    were ever inside sendall() at the same time - the actual byte-level
    interleaving this guards against depends on OS/network timing that's
    unreliable to force in a test, but two threads *entering* sendall()
    concurrently is exactly what the lock in SerialConsole.send() must
    prevent, and that's deterministic to detect directly.
    """

    def __init__(self):
        self._guard = threading.Lock()
        self.active = 0
        self.violation = False

    def sendall(self, data):
        with self._guard:
            self.active += 1
            if self.active > 1:
                self.violation = True
        time.sleep(0.05)
        with self._guard:
            self.active -= 1

    def close(self):
        pass


def test_send_serializes_concurrent_calls(monkeypatch):
    fake_sock = _ConcurrencyDetectingSocket()
    monkeypatch.setattr(
        "qemu_mcp.serial.socket.create_connection", lambda addr, timeout=None: fake_sock
    )
    console = SerialConsole(port=0)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            console.send("x")
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors
    assert not fake_sock.violation


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


def test_close_waits_for_an_in_progress_send_before_closing():
    # close() must share send()'s lock: vm.stop() calls serial_console.close()
    # without waiting for a concurrent qemu_serial_send call the way it waits
    # for qemu_wait_serial/qemu_wait_screen/qemu_screenshot (those mark
    # themselves in_use(), qemu_serial_send doesn't) - so a close() that
    # doesn't itself coordinate with send() could null out self._sock
    # mid-call, turning a clean SerialError into a raw AttributeError.
    # Simulating an in-progress send by holding the lock directly (rather
    # than racing a real blocked socket write) is deterministic, matching
    # test_send_serializes_concurrent_calls above.
    console = SerialConsole(0)
    console._sock = socket.socket()
    closed = threading.Event()

    console._lock.acquire()
    try:
        t = threading.Thread(target=lambda: (console.close(), closed.set()))
        t.start()
        t.join(timeout=0.3)
        assert not closed.is_set(), "close() must block while a send is in flight"
    finally:
        console._lock.release()
    t.join(timeout=2)
    assert closed.is_set()
    assert console._sock is None


def test_send_raises_serial_error_when_the_initial_connect_fails():
    # Port 0 with no listener: connect() fails immediately.
    server, port = _listen()
    server.close()  # free the port again so nothing is listening on it

    console = SerialConsole(port)
    with pytest.raises(SerialError, match=str(port)):
        console.send("hello")
    assert console._sock is None


def test_send_raises_serial_error_when_reconnect_after_a_drop_also_fails(monkeypatch):
    calls = []

    def fake_create_connection(addr, timeout=None):
        calls.append(addr)
        if len(calls) == 1:
            return _FakeSocket(fail=True)
        raise OSError("Connection refused")

    monkeypatch.setattr(
        "qemu_mcp.serial.socket.create_connection", fake_create_connection
    )

    console = SerialConsole(9999)
    with pytest.raises(SerialError, match="lost the connection"):
        console.send("first")

    assert len(calls) == 2
    assert console._sock is None


def test_send_recovers_on_a_later_call_after_a_failed_reconnect(monkeypatch):
    sockets = [_FakeSocket(fail=True), None, _FakeSocket(fail=False)]
    calls = []

    def fake_create_connection(addr, timeout=None):
        calls.append(addr)
        sock = sockets[len(calls) - 1]
        if sock is None:
            raise OSError("Connection refused")
        return sock

    monkeypatch.setattr(
        "qemu_mcp.serial.socket.create_connection", fake_create_connection
    )

    console = SerialConsole(9999)
    with pytest.raises(SerialError):
        console.send("first")  # sockets[0] fails, reconnect (sockets[1]) also fails

    console.send("second")  # fresh connect succeeds this time (sockets[2])
    assert console._sock is sockets[2]
    assert sockets[2].sent == b"second"
