"""Unit tests for qmp.py's QMPClient. No real QEMU needed - QMPClient is
tested against a plain local TCP socket standing in for QEMU's QMP server.
"""

import os
import socket
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp.qmp import QMPClient, QMPError  # noqa: E402


def _fake_qmp_server(hold_open):
    """A QMP server that completes the handshake, then never answers the
    next command - `hold_open` keeps the connection alive so the client's
    next read genuinely times out instead of seeing a closed socket.
    """
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)

    def run():
        conn, _ = server.accept()
        conn.sendall(b'{"QMP": {"version": {}}}\n')
        conn.recv(65536)  # qmp_capabilities
        conn.sendall(b'{"return": {}}\n')
        conn.recv(65536)  # the command under test
        hold_open.wait()
        conn.close()

    threading.Thread(target=run, daemon=True).start()
    return server, port


def test_command_wraps_a_read_timeout_in_qmp_error():
    hold_open = threading.Event()
    server, port = _fake_qmp_server(hold_open)
    try:
        client = QMPClient(port)
        client.sock.settimeout(0.2)
        with pytest.raises(QMPError, match="timed out"):
            client.command("query-status")
    finally:
        hold_open.set()
        client.close()
        server.close()


def test_read_timeout_is_configurable_via_constructor():
    hold_open = threading.Event()
    server, port = _fake_qmp_server(hold_open)
    try:
        client = QMPClient(port, read_timeout=0.2)
        assert client.sock.gettimeout() == 0.2
        with pytest.raises(QMPError, match="timed out"):
            client.command("query-status")
    finally:
        hold_open.set()
        client.close()
        server.close()


def test_command_wraps_a_send_error_in_qmp_error():
    client = QMPClient.__new__(QMPClient)
    client.sock = _RaisingSocket()
    with pytest.raises(QMPError, match="QMP connection error"):
        client.command("query-status")


class _RaisingSocket:
    def sendall(self, data):
        raise OSError("Broken pipe")


def test_read_msg_raises_qmp_error_when_connection_is_closed_by_peer():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    port = server.getsockname()[1]
    server.listen(1)

    def run():
        conn, _ = server.accept()
        conn.sendall(b'{"QMP": {"version": {}}}\n')
        conn.recv(65536)
        conn.sendall(b'{"return": {}}\n')
        conn.close()

    threading.Thread(target=run, daemon=True).start()
    try:
        client = QMPClient(port)
        with pytest.raises(QMPError, match="closed by QEMU"):
            client.command("query-status")
    finally:
        server.close()
