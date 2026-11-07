"""End-to-end smoke test: boots a real guest and exercises every tool.

Needs a bootable image. Point QEMU_MCP_TEST_ISO at any bootable ISO
(a hobby-OS ISO, an Alpine netboot ISO, anything that draws to VGA):

    QEMU_MCP_TEST_ISO=path/to/os.iso python tests/smoke_test.py

qemu_snapshot_save/qemu_snapshot_list/qemu_snapshot_load/qemu_snapshot_delete
need a qcow2 disk instead of an ISO. By default one is created for this run
via qemu_disk_create (blank - savevm/loadvm snapshot RAM+device state, not
disk content, so a real OS on it isn't needed); set QEMU_MCP_TEST_QCOW2 to
use a specific disk instead (e.g. one with a real OS already installed):

    QEMU_MCP_TEST_ISO=path/to/os.iso QEMU_MCP_TEST_QCOW2=path/to/disk.qcow2 \\
        python tests/smoke_test.py

Calls the tool functions directly (no MCP transport) - transport is the
SDK's job; this verifies the QEMU/QMP plumbing on your machine.
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp import server  # noqa: E402

ISO = os.environ.get("QEMU_MCP_TEST_ISO")
if not ISO:
    sys.exit("set QEMU_MCP_TEST_ISO to a bootable ISO path")

ARCH = os.environ.get("QEMU_MCP_TEST_ARCH", "x86_64")
OUT = os.environ.get("QEMU_MCP_TEST_SHOT", os.path.join(os.path.dirname(__file__), "smoke.png"))
DISK = os.environ.get("QEMU_MCP_TEST_QCOW2")  # optional: a qcow2 disk, to also exercise snapshots
CREATED_DISK = None  # set below if DISK wasn't given, so it can be cleaned up at the end

print(server.qemu_version(arch=ARCH))

print(server.qemu_boot(name="smoke", iso=ISO, arch=ARCH, memory_mb=256))
print(server.qemu_list())

print(server.qemu_wait_screen(name="smoke", timeout_s=15, poll_interval_s=1.0, stable_polls=2))

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

print(server.qemu_mouse(name="smoke", x=0.5, y=0.5))
print(server.qemu_mouse(name="smoke", x=0.3, y=0.3, button="left"))

print(server.qemu_pause(name="smoke"))
status = json.loads(server.qemu_qmp(name="smoke", command="query-status"))
assert status.get("running") is False, f"expected paused, query-status said: {status}"
print(server.qemu_resume(name="smoke"))
status = json.loads(server.qemu_qmp(name="smoke", command="query-status"))
assert status.get("running") is True, f"expected running after resume, query-status said: {status}"

# qemu_change_media needs the CD-ROM's block-backend id, which isn't
# guessable ahead of time (depends on machine type/QEMU version) - find it
# via query-block instead of hardcoding one, same as a real caller would.
block_info = json.loads(server.qemu_qmp(name="smoke", command="query-block"))
cdrom = next((b for b in block_info if b.get("removable") and b.get("qdev")), None)
if cdrom:
    # Swap the same ISO back in - exercises the eject+reinsert path without
    # needing a second image file just for this smoke test.
    print(server.qemu_change_media(name="smoke", device=cdrom["qdev"], path=ISO, force=True))
else:
    print("skipping qemu_change_media: no removable block device found via query-block")

# Marker is arbitrary and unlikely to appear - exercises the timeout path
# without assuming anything about what this particular ISO prints.
print(server.qemu_wait_serial(name="smoke", text="qemu-mcp-smoke-marker", timeout_s=2))

print(server.qemu_serial_send(name="smoke", text="\n"))
time.sleep(1)
print("serial tail:", server.qemu_serial(name="smoke", tail_lines=5)[:400])
print(server.qemu_qmp(name="smoke", command="query-status"))
print(server.qemu_stop(name="smoke", force=True))
print(server.qemu_list())

if not DISK:
    CREATED_DISK = os.path.join(tempfile.mkdtemp(prefix="qemu-mcp-smoke-"), "smoke.qcow2")
    print(server.qemu_disk_create(path=CREATED_DISK, size="64M"))
    DISK = CREATED_DISK

print(server.qemu_boot(name="smoke-snap", disk=DISK, arch=ARCH, memory_mb=256))
print(server.qemu_snapshot_save(name="smoke-snap", tag="smoke-tag"))
print(server.qemu_snapshot_list(name="smoke-snap"))
print(server.qemu_snapshot_load(name="smoke-snap", tag="smoke-tag"))
print(server.qemu_snapshot_delete(name="smoke-snap", tag="smoke-tag"))
print(server.qemu_stop(name="smoke-snap", force=True))

if CREATED_DISK:
    os.remove(CREATED_DISK)
    os.rmdir(os.path.dirname(CREATED_DISK))

print("SMOKE OK")
