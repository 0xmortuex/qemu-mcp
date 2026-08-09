"""Unit tests for vm.find_qemu's missing-binary error and vm.disk_format. No QEMU needed."""

import os
import stat
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp import vm  # noqa: E402


def _make_fake_binary(directory, name):
    # shutil.which() only recognizes PATHEXT-suffixed files on Windows, unlike
    # POSIX where the executable bit alone is enough - match real qemu installs.
    if sys.platform == "win32" and not name.lower().endswith(".exe"):
        name += ".exe"
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


def test_find_qemu_missing_lists_other_installed_arches(tmp_path, monkeypatch):
    _make_fake_binary(tmp_path, "qemu-system-aarch64")
    _make_fake_binary(tmp_path, "qemu-system-riscv64")
    monkeypatch.setenv("PATH", str(tmp_path))

    try:
        vm.find_qemu("x86_64")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        message = str(e)
        assert "qemu-system-x86_64" in message
        assert "aarch64" in message
        assert "riscv64" in message


def test_find_qemu_missing_reports_none_found(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    try:
        vm.find_qemu("x86_64")
        assert False, "expected FileNotFoundError"
    except FileNotFoundError as e:
        assert "No qemu-system-* binaries found" in str(e)


def test_find_qemu_finds_exact_match_on_path(tmp_path, monkeypatch):
    path = _make_fake_binary(tmp_path, "qemu-system-x86_64")
    monkeypatch.setenv("PATH", str(tmp_path))

    # normcase: shutil.which() resolves the PATHEXT suffix itself on Windows
    # and may return it in a different case (".EXE") than the file we made.
    assert os.path.normcase(vm.find_qemu("x86_64")) == os.path.normcase(path)


def test_disk_format_detects_qcow2_magic(tmp_path):
    path = tmp_path / "disk.img"
    path.write_bytes(b"QFI\xfbsomeqcow2headerbytes...")
    assert vm.disk_format(str(path)) == "qcow2"


def test_disk_format_defaults_to_raw(tmp_path):
    path = tmp_path / "disk.img"
    path.write_bytes(b"\x00" * 512)
    assert vm.disk_format(str(path)) == "raw"


def test_disk_format_missing_file_defaults_to_raw(tmp_path):
    assert vm.disk_format(str(tmp_path / "does-not-exist.img")) == "raw"


class _FakeProc:
    """Stands in for subprocess.Popen: already exited, no real process involved."""

    returncode = 0
    pid = -1

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def kill(self):
        pass


class _FakeQMP:
    def command(self, name, **kwargs):
        raise vm.QMPError("no real QEMU in this test")

    def close(self):
        pass


class _FakeSerial:
    def close(self):
        pass


def _register_fake_vm(name, workdir, arch="x86_64", machine=None):
    fake = vm.VM(
        name=name,
        proc=_FakeProc(),
        qmp=_FakeQMP(),
        workdir=str(workdir),
        serial_path=str(workdir / "serial.log"),
        serial_console=_FakeSerial(),
        qemu_log=str(workdir / "qemu.log"),
        cmdline=["qemu-system-x86_64"],
        arch=arch,
        machine=machine,
    )
    vm._vms[name] = fake
    return fake


def test_stop_removes_the_vm_workdir(tmp_path):
    workdir = tmp_path / "qemu-mcp-test"
    workdir.mkdir()
    (workdir / "serial.log").write_text("hello")
    _register_fake_vm("cleanup-test", workdir)

    try:
        outcome = vm.stop("cleanup-test", force=True)
    finally:
        vm._vms.pop("cleanup-test", None)

    assert outcome == "already exited"
    assert not workdir.exists()


def test_qemu_list_reports_arch_and_machine(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-list-test"
    workdir.mkdir()
    _register_fake_vm("list-test", workdir, arch="aarch64", machine="virt")

    try:
        rows = server.qemu_list()
    finally:
        vm._vms.pop("list-test", None)

    assert "list-test" in rows
    assert "aarch64" in rows
    assert "-M virt" in rows


def test_qemu_list_omits_machine_note_when_unset(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-list-test2"
    workdir.mkdir()
    _register_fake_vm("list-test2", workdir, arch="x86_64", machine=None)

    try:
        rows = server.qemu_list()
    finally:
        vm._vms.pop("list-test2", None)

    line = next(r for r in rows.splitlines() if r.startswith("list-test2:"))
    assert "x86_64" in line
    assert "-M" not in line


def _make_fake_qemu_script(directory, body):
    """A fake qemu-system-x86_64 that runs `body` instead of real QEMU."""
    name = "qemu-system-x86_64"
    path = os.path.join(directory, name)
    with open(path, "w") as f:
        f.write(f"#!/bin/sh\n{body}\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    return path


class _RaisingQMPClient:
    """Stands in for QMPClient: always fails to connect, after a short delay
    so the "QEMU exited immediately" branch's proc.poll() check is reliable."""

    def __init__(self, port, connect_timeout=20.0):
        time.sleep(0.3)
        raise vm.QMPError("simulated: QMP never came up")


def _track_mkdtemp(monkeypatch):
    """Record every workdir vm.boot() creates via tempfile.mkdtemp, so a test
    can assert it was cleaned up without vm.boot() returning it on failure."""
    created = []
    orig = vm.tempfile.mkdtemp

    def _tracking(*args, **kwargs):
        d = orig(*args, **kwargs)
        created.append(d)
        return d

    monkeypatch.setattr(vm.tempfile, "mkdtemp", _tracking)
    return created


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_cleans_up_workdir_when_qemu_exits_immediately(tmp_path, monkeypatch):
    _make_fake_qemu_script(tmp_path, "exit 1")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(vm, "QMPClient", _RaisingQMPClient)
    created = _track_mkdtemp(monkeypatch)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        vm.boot(
            name="boot-fail-immediate", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "QEMU exited immediately" in str(e)

    assert "boot-fail-immediate" not in vm._vms
    assert created and not os.path.exists(created[-1])


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_cleans_up_workdir_when_qmp_never_connects(tmp_path, monkeypatch):
    _make_fake_qemu_script(tmp_path, "sleep 5")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(vm, "QMPClient", _RaisingQMPClient)
    created = _track_mkdtemp(monkeypatch)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        vm.boot(
            name="boot-fail-hang", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert False, "expected QMPError"
    except vm.QMPError:
        pass

    assert "boot-fail-hang" not in vm._vms
    assert created and not os.path.exists(created[-1])
