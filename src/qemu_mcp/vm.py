"""VM lifecycle: find QEMU, launch it with QMP + file-backed serial, track it."""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field

from .qmp import QMPClient, QMPError

_WINDOWS_QEMU_DIRS = [
    r"C:\Program Files\qemu",
    r"C:\Program Files (x86)\qemu",
]


def _installed_arches() -> list[str]:
    """Scan PATH (and the Windows QEMU dirs) for other qemu-system-* binaries."""
    dirs = os.environ.get("PATH", "").split(os.pathsep)
    if sys.platform == "win32":
        dirs = [os.environ.get("QEMU_DIR"), *_WINDOWS_QEMU_DIRS, *dirs]
    found = set()
    for directory in dirs:
        if not directory:
            continue
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for entry in entries:
            name = entry[:-4] if sys.platform == "win32" and entry.lower().endswith(".exe") else entry
            if name.startswith("qemu-system-"):
                found.add(name[len("qemu-system-"):])
    return sorted(found)


def find_qemu(arch: str) -> str:
    exe = f"qemu-system-{arch}"
    path = shutil.which(exe)
    if path:
        return path
    if sys.platform == "win32":
        for base in [os.environ.get("QEMU_DIR"), *_WINDOWS_QEMU_DIRS]:
            if base and os.path.isfile(os.path.join(base, exe + ".exe")):
                return os.path.join(base, exe + ".exe")
    found = _installed_arches()
    hint = (
        f" Found on this system: {', '.join(found)}."
        if found
        else " No qemu-system-* binaries found anywhere on this system."
    )
    raise FileNotFoundError(
        f"{exe} not found. Install QEMU and put it on PATH "
        f"(or set QEMU_DIR on Windows).{hint}"
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class VM:
    name: str
    proc: subprocess.Popen
    qmp: QMPClient
    workdir: str
    serial_path: str
    qemu_log: str
    cmdline: list[str]
    started_at: float = field(default_factory=time.monotonic)

    @property
    def running(self) -> bool:
        return self.proc.poll() is None

    def serial_text(self) -> str:
        try:
            with open(self.serial_path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""


_vms: dict[str, VM] = {}


def get_vm(name: str) -> VM:
    vm = _vms.get(name)
    if vm is None:
        known = ", ".join(_vms) or "none"
        raise KeyError(f"no VM named {name!r} (running VMs: {known})")
    if not vm.running:
        raise RuntimeError(
            f"VM {name!r} has exited (code {vm.proc.returncode}). "
            f"Last serial output:\n{tail(vm.serial_text(), 15)}"
        )
    return vm


def list_vms() -> list[VM]:
    return list(_vms.values())


def tail(text: str, lines: int) -> str:
    return "\n".join(text.splitlines()[-lines:])


def boot(
    name: str,
    arch: str,
    memory_mb: int,
    iso: str | None,
    kernel: str | None,
    append: str | None,
    initrd: str | None,
    disk: str | None,
    extra_args: str | None,
    machine: str | None = None,
) -> VM:
    stale = _vms.get(name)
    if stale is not None:
        if stale.running:
            raise RuntimeError(f"a VM named {name!r} is already running - stop it first")
        del _vms[name]

    if not (iso or kernel or disk):
        raise ValueError("nothing to boot: give at least one of iso, kernel, disk")
    for label, p in (("iso", iso), ("kernel", kernel), ("initrd", initrd), ("disk", disk)):
        if p and not os.path.isfile(p):
            raise FileNotFoundError(f"{label} not found: {p}")

    qemu = find_qemu(arch)
    port = _free_port()
    workdir = tempfile.mkdtemp(prefix=f"qemu-mcp-{name}-")
    serial_path = os.path.join(workdir, "serial.log")
    qemu_log = os.path.join(workdir, "qemu.log")

    args = [
        qemu,
        "-name", name,
        "-m", str(memory_mb),
        "-display", "none",
        "-qmp", f"tcp:127.0.0.1:{port},server,nowait",
        "-serial", f"file:{serial_path}",
    ]
    if machine:
        args += ["-M", machine]
    if iso:
        args += ["-cdrom", iso, "-boot", "d"]
    if kernel:
        args += ["-kernel", kernel]
    if append:
        args += ["-append", append]
    if initrd:
        args += ["-initrd", initrd]
    if disk:
        args += ["-drive", f"file={disk},format=raw"]
    if extra_args:
        args += shlex.split(extra_args, posix=(os.name != "nt"))

    log = open(qemu_log, "w", encoding="utf-8")
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)

    try:
        qmp = QMPClient(port)
    except QMPError:
        if proc.poll() is not None:
            log.close()
            with open(qemu_log, encoding="utf-8", errors="replace") as f:
                detail = f.read().strip()
            raise RuntimeError(
                f"QEMU exited immediately (code {proc.returncode}):\n{detail}"
            ) from None
        proc.kill()
        raise

    vm = VM(
        name=name, proc=proc, qmp=qmp, workdir=workdir,
        serial_path=serial_path, qemu_log=qemu_log, cmdline=args,
    )
    _vms[name] = vm
    return vm


def stop(name: str, force: bool) -> str:
    vm = _vms.get(name)
    if vm is None:
        raise KeyError(f"no VM named {name!r}")
    outcome = "already exited"
    if vm.running:
        if not force:
            try:
                vm.qmp.command("system_powerdown")
                outcome = "ACPI powerdown"
            except QMPError:
                force = True
            for _ in range(40):  # up to 10 s for a graceful guest shutdown
                if not vm.running:
                    break
                time.sleep(0.25)
        if vm.running:
            try:
                vm.qmp.command("quit")
            except QMPError:
                pass
            try:
                vm.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                vm.proc.kill()
            outcome = "killed" if force else "ACPI ignored, killed"
    vm.qmp.close()
    del _vms[name]
    return outcome
