"""End-to-end smoke test: boots a real guest and exercises every tool.

Needs a bootable image. Point QEMU_MCP_TEST_ISO at any bootable ISO
(a hobby-OS ISO, an Alpine netboot ISO, anything that draws to VGA):

    QEMU_MCP_TEST_ISO=path/to/os.iso python tests/smoke_test.py

Calls the tool functions directly (no MCP transport) - transport is the
SDK's job; this verifies the QEMU/QMP plumbing on your machine.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp import server  # noqa: E402

ISO = os.environ.get("QEMU_MCP_TEST_ISO")
if not ISO:
    sys.exit("set QEMU_MCP_TEST_ISO to a bootable ISO path")

ARCH = os.environ.get("QEMU_MCP_TEST_ARCH", "x86_64")
OUT = os.environ.get("QEMU_MCP_TEST_SHOT", os.path.join(os.path.dirname(__file__), "smoke.png"))

print(server.qemu_boot(name="smoke", iso=ISO, arch=ARCH, memory_mb=256))
print(server.qemu_list())

time.sleep(8)  # let the guest reach its first screen

shot = server.qemu_screenshot(name="smoke")
png = shot.data
assert png[:8] == b"\x89PNG\r\n\x1a\n", "screendump did not produce a PNG"
with open(OUT, "wb") as f:
    f.write(png)
print(f"screenshot 1: {len(png)} bytes -> {OUT}")

print(server.qemu_key(name="smoke", combo="esc"))
print(server.qemu_type(name="smoke", text="help\n"))
time.sleep(1)
print(server.qemu_type(name="smoke", text="help\n"))
time.sleep(1)

shot2 = server.qemu_screenshot(name="smoke")
with open(OUT.replace(".png", "-2.png"), "wb") as f:
    f.write(shot2.data)
print(f"screenshot 2: {len(shot2.data)} bytes")

print(server.qemu_serial_send(name="smoke", text="\n"))
time.sleep(1)
print("serial tail:", server.qemu_serial(name="smoke", tail_lines=5)[:400])
print(server.qemu_qmp(name="smoke", command="query-status"))
print(server.qemu_stop(name="smoke", force=True))
print(server.qemu_list())
print("SMOKE OK")
