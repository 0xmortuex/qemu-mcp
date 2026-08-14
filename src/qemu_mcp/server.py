"""qemu-mcp: an MCP server that lets an AI agent boot and drive QEMU VMs."""

from __future__ import annotations

import io
import json
import os
import time
from typing import Any

from mcp.server.mcpserver import Image, MCPServer

from . import keys as keymod
from . import mouse as mousemod
from . import screen as screenmod
from . import snapshot as snapmod
from . import vm as vmmod

mcp = MCPServer(
    "qemu",
    instructions=(
        "Boot and drive QEMU virtual machines: boot an ISO/kernel/disk, "
        "type into the guest, take screenshots, read the serial console, "
        "and wait for boot markers. Typical loop: qemu_boot -> "
        "qemu_wait_serial or a short pause -> qemu_screenshot -> "
        "qemu_type / qemu_key -> qemu_screenshot -> qemu_stop. "
        "Screenshots show the guest's VGA display even though the VM "
        "runs headless."
    ),
)


@mcp.tool()
def qemu_boot(
    name: str,
    iso: str | None = None,
    kernel: str | None = None,
    append: str | None = None,
    initrd: str | None = None,
    disk: str | None = None,
    arch: str = "x86_64",
    memory_mb: int = 256,
    extra_args: str | None = None,
    machine: str | None = None,
    qmp_connect_timeout_s: float = 20.0,
    qmp_read_timeout_s: float = 15.0,
) -> str:
    """Boot a QEMU VM headless and register it under `name`.

    name identifies this VM in all later calls (qemu_screenshot, qemu_stop,
    etc.) - it must be non-empty and contain no "/" or "\\" (it also names a
    temp directory and is passed to QEMU's -name flag).
    Provide at least one of: iso (bootable CD image), kernel (multiboot/bzImage,
    optionally with append/initrd), or disk (raw or qcow2 disk image, auto-detected;
    qcow2 is required for qemu_snapshot_save/qemu_snapshot_load). memory_mb must
    be positive. arch picks the
    qemu-system-<arch> binary (x86_64, i386, aarch64, riscv64...). machine is
    passed as QEMU's -M and is required on some archs - aarch64 and riscv64
    have no default machine and need e.g. machine="virt". extra_args is passed
    to QEMU verbatim, e.g. "-netdev user,id=n0 -device rtl8139,netdev=n0".
    qmp_connect_timeout_s bounds how long to retry connecting to QEMU's QMP
    socket after launch (raise it on a slow/loaded host where QEMU's first
    launch is slow, e.g. under AV scanning). qmp_read_timeout_s bounds how
    long any single QMP command (including ones issued by other qemu_* tools
    for this VM, like qemu_qmp or qemu_snapshot_save) waits for a response -
    raise it if you expect a command that can legitimately run long.
    The VM keeps running until qemu_stop; serial output is captured continuously.
    """
    vm = vmmod.boot(
        name, arch, memory_mb, iso, kernel, append, initrd, disk, extra_args, machine,
        qmp_connect_timeout_s, qmp_read_timeout_s,
    )
    machine_note = f", -M {machine}" if machine else ""
    return (
        f"VM {name!r} booted (pid {vm.proc.pid}, {arch}, {memory_mb} MB{machine_note}).\n"
        f"Serial log: {vm.serial_path}\n"
        f"Next: qemu_wait_serial for a boot marker, or qemu_screenshot to see the display."
    )


@mcp.tool()
def qemu_screenshot(name: str) -> Image:
    """Capture the VM's display as a PNG image.

    Works headless - the guest's VGA framebuffer is captured via QMP
    screendump. Use it to see boot screens, kernel panics, GUIs, or a
    text console that doesn't write to serial.
    """
    from PIL import Image as PILImage

    vm = vmmod.get_vm(name)
    ppm = os.path.join(vm.workdir, "shot.ppm")
    vm.qmp.command("screendump", filename=ppm)
    # QMP returns before the file write is guaranteed visible; poll briefly.
    for _ in range(20):
        if os.path.isfile(ppm) and os.path.getsize(ppm) > 0:
            break
        time.sleep(0.05)
    with PILImage.open(ppm) as im:
        buf = io.BytesIO()
        im.save(buf, format="PNG")
    return Image(data=buf.getvalue(), format="png")


@mcp.tool()
def qemu_type(name: str, text: str, delay_ms: int = 35) -> str:
    """Type text into the guest as keyboard input. "\\n" presses Enter.

    Handles US-layout characters including shifted symbols. delay_ms is the
    gap between keystrokes - raise it (e.g. 80) if the guest drops
    characters during early boot.
    """
    vm = vmmod.get_vm(name)
    for ch in text:
        qcodes = keymod.char_to_keys(ch)
        vm.qmp.command(
            "send-key",
            keys=[{"type": "qcode", "data": q} for q in qcodes],
        )
        time.sleep(delay_ms / 1000)
    return f"typed {len(text)} characters into {name!r}"


@mcp.tool()
def qemu_key(name: str, combo: str) -> str:
    """Press a key or chord: "enter", "esc", "f12", "ctrl-alt-f2", "ctrl-c"...

    Parts are joined with "-" and pressed together. Use qemu_type for
    plain text.
    """
    vm = vmmod.get_vm(name)
    qcodes = keymod.parse_combo(combo)
    vm.qmp.command("send-key", keys=[{"type": "qcode", "data": q} for q in qcodes])
    return f"pressed {combo} in {name!r}"


@mcp.tool()
def qemu_mouse(name: str, x: float, y: float, button: str | None = None) -> str:
    """Move the absolute pointer and optionally click.

    x and y are fractions of the screen width/height (0.0 = left/top, 1.0 =
    right/bottom) - read them off a qemu_screenshot. button is "left",
    "right", or "middle" for a full click at that position; omit it to just
    move the pointer. Needs the guest to have an absolute pointer (USB
    tablet or PS/2 mouse) to track it - most GUIs have one by default.
    """
    vm = vmmod.get_vm(name)
    events = mousemod.click_events(x, y, button) if button else mousemod.move_events(x, y)
    vm.qmp.command("input-send-event", events=events)
    action = f"clicked {button}" if button else "moved"
    return f"{action} at ({x:.2f}, {y:.2f}) in {name!r}"


@mcp.tool()
def qemu_snapshot_save(name: str, tag: str) -> str:
    """Save a full VM snapshot (RAM + device state) under `tag`.

    Uses QEMU's internal savevm mechanism, which stores the snapshot inside
    the disk image itself - the VM's disk must be qcow2 (raw images do not
    support internal snapshots). Saving again with the same tag overwrites
    it. tag may only contain letters, digits, '.', '_', '-'.
    """
    vm = vmmod.get_vm(name)
    vm.qmp.command("human-monitor-command", **{"command-line": snapmod.save_command_line(tag)})
    return f"saved snapshot {tag!r} for VM {name!r}"


@mcp.tool()
def qemu_snapshot_load(name: str, tag: str) -> str:
    """Restore a VM to a snapshot previously saved with qemu_snapshot_save.

    Requires the same qcow2 disk the snapshot was taken on.
    """
    vm = vmmod.get_vm(name)
    vm.qmp.command("human-monitor-command", **{"command-line": snapmod.load_command_line(tag)})
    return f"loaded snapshot {tag!r} for VM {name!r}"


@mcp.tool()
def qemu_serial(name: str, tail_lines: int = 50) -> str:
    """Read the tail of the VM's serial console output (COM1)."""
    vm = vmmod.get_vm(name)
    text = vm.serial_text()
    if not text:
        return "(no serial output yet)"
    return vmmod.tail(text, tail_lines)


@mcp.tool()
def qemu_serial_send(name: str, text: str) -> str:
    """Write text to the guest's serial console (COM1).

    For guests that only expose a shell over serial (no VGA console, or a
    kernel with a serial-only debug shell) - the bidirectional counterpart
    to qemu_serial's read-only tail. Sent exactly as given; include "\\n"
    yourself for Enter. Kept on one persistent connection for the VM's
    lifetime - disconnecting and reconnecting would hang up the serial line.
    """
    vm = vmmod.get_vm(name)
    vm.serial_console.send(text)
    return f"sent {len(text)} bytes to {name!r}'s serial console"


@mcp.tool()
def qemu_wait_serial(name: str, text: str, timeout_s: int = 30) -> str:
    """Block until `text` appears on the serial console, or time out.

    The reliable way to know a guest reached a boot stage ("login:",
    "kernel ready", a shell prompt) before typing or screenshotting.
    Returns the serial tail either way, prefixed FOUND or TIMEOUT.
    """
    vm = vmmod.get_vm(name)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        out = vm.serial_text()
        if text in out:
            return "FOUND\n" + vmmod.tail(out, 20)
        if not vm.running:
            return "VM EXITED\n" + vmmod.tail(out, 20)
        time.sleep(0.25)
    return "TIMEOUT\n" + vmmod.tail(vm.serial_text(), 20)


@mcp.tool()
def qemu_wait_screen(
    name: str, timeout_s: int = 30, poll_interval_s: float = 1.0, stable_polls: int = 3
) -> str:
    """Block until the VM's display stops changing, or time out.

    Polls screendumps every poll_interval_s and waits for `stable_polls`
    consecutive identical frames - the reliable way to know a VGA-only
    guest (no serial output) has finished a BIOS splash or boot animation
    before you screenshot or type. For guests with serial output, prefer
    qemu_wait_serial - it doesn't need a fixed number of polls to decide.
    """
    vm = vmmod.get_vm(name)
    tracker = screenmod.StabilityTracker(stable_polls)
    ppm = os.path.join(vm.workdir, "wait_screen.ppm")
    deadline = time.monotonic() + timeout_s
    polls = 0
    while time.monotonic() < deadline:
        vm.qmp.command("screendump", filename=ppm)
        for _ in range(20):
            if os.path.isfile(ppm) and os.path.getsize(ppm) > 0:
                break
            time.sleep(0.05)
        polls += 1
        if tracker.update(screenmod.hash_file(ppm)):
            return f"SETTLED after {polls} polls ({stable_polls} identical frames)"
        if not vm.running:
            return f"VM EXITED after {polls} polls"
        time.sleep(poll_interval_s)
    return f"TIMEOUT after {timeout_s}s ({polls} polls)"


@mcp.tool()
def qemu_list() -> str:
    """List all VMs managed by this server, with arch, machine, pid, uptime, and state.

    A VM that exited on its own (guest panic, or `quit` via qemu_qmp) is
    shown here once as exited(...), then reaped - its workdir and handles
    are freed before this call returns, so it won't reappear next time.
    """
    vms = vmmod.list_vms()
    if not vms:
        return "no VMs"
    rows = []
    for vm in vms:
        state = "running" if vm.running else f"exited({vm.proc.returncode})"
        machine_note = f" -M {vm.machine}" if vm.machine else ""
        rows.append(
            f"{vm.name}: {state}, {vm.arch}{machine_note}, pid {vm.proc.pid}, "
            f"up {int(time.monotonic() - vm.started_at)}s, "
            f"serial {os.path.getsize(vm.serial_path) if os.path.isfile(vm.serial_path) else 0} bytes"
        )
    vmmod.reap_dead()
    return "\n".join(rows)


@mcp.tool()
def qemu_stop(name: str, force: bool = False) -> str:
    """Stop a VM. Tries graceful ACPI powerdown first; force=True kills it.

    Guests without ACPI handling (most hobby kernels) will need force=True
    or will be killed after the 10 s grace period anyway.
    """
    outcome = vmmod.stop(name, force)
    return f"VM {name!r} stopped ({outcome})"


@mcp.tool()
def qemu_qmp(name: str, command: str, arguments: dict[str, Any] | None = None) -> str:
    """Escape hatch: run a raw QMP command on the VM.

    Examples: query-status, system_reset, memsave, device_add. See the QEMU
    QMP reference for commands and their arguments.
    """
    vm = vmmod.get_vm(name)
    result = vm.qmp.command(command, **(arguments or {}))
    return json.dumps(result, indent=2, default=str)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
