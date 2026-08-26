"""MCP stdio handshake smoke test: spawns the real server subprocess over
stdio, initializes a client session, and checks the tool list. No QEMU
needed - this only exercises the MCP transport/registration, never boots a VM.
"""

import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

EXPECTED_TOOLS = {
    "qemu_boot",
    "qemu_screenshot",
    "qemu_type",
    "qemu_key",
    "qemu_mouse",
    "qemu_snapshot_save",
    "qemu_snapshot_load",
    "qemu_snapshot_delete",
    "qemu_snapshot_list",
    "qemu_serial",
    "qemu_serial_send",
    "qemu_wait_serial",
    "qemu_wait_screen",
    "qemu_list",
    "qemu_stop",
    "qemu_qmp",
}


@pytest.mark.anyio
async def test_stdio_handshake_lists_expected_tools():
    params = StdioServerParameters(command=sys.executable, args=["-m", "qemu_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init_result = await session.initialize()
        assert init_result.server_info.name == "qemu"

        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert EXPECTED_TOOLS <= names


@pytest.fixture
def anyio_backend():
    return "asyncio"
