"""Every tool's behaviour hints, as an MCP client receives them over stdio.

Clients use readOnlyHint/destructiveHint/idempotentHint/openWorldHint to
decide when to ask the user before a call, and some directories reject tools
that leave any of them unset. This pins each tool's four values, so changing
what a tool does without updating its hints (or the reverse) fails here. The
reasoning behind the non-obvious values is next to each tool in server.py.
No QEMU needed.
"""

import sys

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

HINTS = {
    #                        read_only destructive idempotent open_world
    "qemu_boot":            (False,    True,       False,     True),
    "qemu_version":         (True,     False,      True,      False),
    "qemu_screenshot":      (True,     False,      True,      False),
    "qemu_type":            (False,    True,       False,     False),
    "qemu_key":             (False,    True,       False,     False),
    "qemu_mouse":           (False,    True,       False,     False),
    "qemu_snapshot_save":   (False,    True,       False,     False),
    "qemu_snapshot_load":   (False,    True,       True,      False),
    "qemu_snapshot_delete": (False,    True,       True,      False),
    "qemu_snapshot_list":   (True,     False,      True,      False),
    "qemu_serial":          (True,     False,      True,      False),
    "qemu_serial_send":     (False,    True,       False,     False),
    "qemu_wait_serial":     (True,     False,      False,     False),
    "qemu_wait_screen":     (True,     False,      True,      False),
    "qemu_list":            (False,    True,       True,      False),
    "qemu_stop":            (False,    True,       True,      False),
    "qemu_qmp":             (False,    True,       False,     True),
}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_every_tool_declares_its_four_hints():
    params = StdioServerParameters(command=sys.executable, args=["-m", "qemu_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = {t.name: t for t in (await session.list_tools()).tools}

    assert set(tools) == set(HINTS)
    for name, want in HINTS.items():
        a = tools[name].annotations
        assert a is not None, f"{name} has no annotations"
        got = (a.read_only_hint, a.destructive_hint, a.idempotent_hint, a.open_world_hint)
        assert got == want, f"{name}: got {got}, want {want}"
