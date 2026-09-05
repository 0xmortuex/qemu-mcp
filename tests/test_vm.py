"""Unit tests for vm.find_qemu's missing-binary error and vm.disk_format. No QEMU needed."""

import os
import shutil
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


@pytest.mark.parametrize("name", ["", "foo/bar", "foo\\bar", ".", ".."])
def test_boot_rejects_invalid_names(name):
    try:
        vm.boot(
            name=name, arch="x86_64", memory_mb=64,
            iso="whatever", kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert repr(name) in str(e)


@pytest.mark.parametrize("memory_mb", [0, -1, -256])
def test_boot_rejects_non_positive_memory_mb(memory_mb):
    try:
        vm.boot(
            name="valid-name", arch="x86_64", memory_mb=memory_mb,
            iso="whatever", kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert repr(memory_mb) in str(e)


@pytest.mark.parametrize("qmp_connect_timeout_s", [0, -1.0, -5])
def test_boot_rejects_non_positive_qmp_connect_timeout(qmp_connect_timeout_s):
    try:
        vm.boot(
            name="valid-name", arch="x86_64", memory_mb=64,
            iso="whatever", kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
            qmp_connect_timeout_s=qmp_connect_timeout_s,
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert repr(qmp_connect_timeout_s) in str(e)


@pytest.mark.parametrize("qmp_read_timeout_s", [0, -1.0, -5])
def test_boot_rejects_non_positive_qmp_read_timeout(qmp_read_timeout_s):
    # Regression test: socket.settimeout() raises a raw ValueError (not
    # QMPError) for non-positive values, which used to escape vm.boot()'s
    # `except QMPError` uncaught *after* QEMU was already launched - leaking
    # the process, its QMP socket, and the workdir. Confirmed directly:
    #   >>> socket.socket().settimeout(-1.0)
    #   ValueError: Timeout value out of range
    # Validating up front (before find_qemu/Popen) avoids ever reaching that
    # path, so this test only needs to check the early rejection.
    try:
        vm.boot(
            name="valid-name", arch="x86_64", memory_mb=64,
            iso="whatever", kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
            qmp_read_timeout_s=qmp_read_timeout_s,
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert repr(qmp_read_timeout_s) in str(e)


@pytest.mark.parametrize("extra_args", ['-device foo "bar', "'unterminated"])
def test_boot_rejects_malformed_extra_args(extra_args):
    # Regression test: shlex.split() raises a raw ValueError (not caught
    # anywhere) for unbalanced quotes, which used to happen *after*
    # tempfile.mkdtemp() had already created the VM's workdir - since
    # nothing on that path cleans up on failure, every malformed extra_args
    # call leaked a workdir. Validating up front (before mkdtemp is ever
    # called) avoids the leak entirely, so this test only needs to check
    # the early rejection; test_boot_does_not_create_workdir_for_bad_extra_args
    # below confirms mkdtemp is never reached.
    try:
        vm.boot(
            name="valid-name", arch="x86_64", memory_mb=64,
            iso="whatever", kernel=None, append=None, initrd=None,
            disk=None, extra_args=extra_args,
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert repr(extra_args) in str(e)


def test_boot_does_not_create_workdir_for_bad_extra_args(monkeypatch):
    created = _track_mkdtemp(monkeypatch)
    try:
        vm.boot(
            name="valid-name", arch="x86_64", memory_mb=64,
            iso="whatever", kernel=None, append=None, initrd=None,
            disk=None, extra_args='-device foo "bar',
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
    assert created == []


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


class _QuitExitsProc(_FakeProc):
    """Running until quit()/kill() is called, then reports exited."""

    def __init__(self):
        self._running = True

    def poll(self):
        return None if self._running else 0

    def wait(self, timeout=None):
        self._running = False
        return 0

    def kill(self):
        self._running = False


class _PowerdownFailsQMP(_FakeQMP):
    """system_powerdown fails outright (e.g. a broken QMP connection); quit succeeds."""

    def __init__(self):
        self.calls = []

    def command(self, name, **kwargs):
        self.calls.append(name)
        if name == "system_powerdown":
            raise vm.QMPError("qmp unreachable")
        return {}


def test_stop_skips_the_graceful_wait_when_powerdown_itself_fails(tmp_path, monkeypatch):
    # If system_powerdown never reached the guest, waiting up to 10 s for a
    # graceful shutdown that was never requested just delays the fallback
    # kill - regression test for that wasted wait.
    workdir = tmp_path / "qemu-mcp-stop-test"
    workdir.mkdir()
    fake = _register_fake_vm("stop-test", workdir)
    fake.proc = _QuitExitsProc()
    fake.qmp = _PowerdownFailsQMP()

    sleep_calls = []
    monkeypatch.setattr(vm.time, "sleep", lambda s: sleep_calls.append(s))

    try:
        outcome = vm.stop("stop-test", force=False)
    finally:
        vm._vms.pop("stop-test", None)

    assert outcome == "killed"
    assert fake.qmp.calls == ["system_powerdown", "quit"]
    assert sleep_calls == [], "should not sleep waiting for a shutdown that was never requested"


class _RunningFakeProc(_FakeProc):
    def poll(self):
        return None


def test_reap_dead_removes_exited_vms_and_keeps_running_ones(tmp_path):
    dead_workdir = tmp_path / "dead"
    dead_workdir.mkdir()
    _register_fake_vm("dead-vm", dead_workdir)

    alive_workdir = tmp_path / "alive"
    alive_workdir.mkdir()
    alive = _register_fake_vm("alive-vm", alive_workdir)
    alive.proc = _RunningFakeProc()

    try:
        reaped = vm.reap_dead()
        assert reaped == ["dead-vm"]
        assert "dead-vm" not in vm._vms
        assert not dead_workdir.exists()
        assert "alive-vm" in vm._vms
        assert alive_workdir.exists()
    finally:
        vm._vms.pop("dead-vm", None)
        still_alive = vm._vms.pop("alive-vm", None)
        if still_alive is not None:
            shutil.rmtree(still_alive.workdir, ignore_errors=True)


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


def test_qemu_list_shows_an_exited_vm_once_then_reaps_it(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-reap-test"
    workdir.mkdir()
    _register_fake_vm("reap-test", workdir)

    try:
        first = server.qemu_list()
        assert "reap-test" in first
        assert "exited(0)" in first
        assert not workdir.exists()
        assert "reap-test" not in vm._vms

        second = server.qemu_list()
        assert "reap-test" not in second
    finally:
        vm._vms.pop("reap-test", None)


def test_get_vm_raises_for_an_exited_vm(tmp_path):
    workdir = tmp_path / "qemu-mcp-getvm-test"
    workdir.mkdir()
    _register_fake_vm("getvm-test", workdir)

    try:
        try:
            vm.get_vm("getvm-test")
            assert False, "expected RuntimeError"
        except RuntimeError as e:
            assert "has exited" in str(e)
    finally:
        vm._vms.pop("getvm-test", None)


def test_get_vm_any_returns_an_exited_vm_without_raising(tmp_path):
    workdir = tmp_path / "qemu-mcp-getvmany-test"
    workdir.mkdir()
    registered = _register_fake_vm("getvmany-test", workdir)

    try:
        assert vm.get_vm_any("getvmany-test") is registered
    finally:
        vm._vms.pop("getvmany-test", None)


def test_get_vm_any_raises_keyerror_for_an_unregistered_name():
    try:
        vm.get_vm_any("no-such-vm")
        assert False, "expected KeyError"
    except KeyError as e:
        assert "no-such-vm" in str(e)


class _ScreendumpQMP(_FakeQMP):
    """Writes fixed PPM bytes to whatever filename screendump is given."""

    def __init__(self, ppm_bytes):
        self.ppm_bytes = ppm_bytes
        self.filenames = []

    def command(self, name, **kwargs):
        assert name == "screendump"
        filename = kwargs["filename"]
        self.filenames.append(filename)
        with open(filename, "wb") as f:
            f.write(self.ppm_bytes)
        return {}


_ONE_PIXEL_PPM = b"P6\n1 1\n255\n" + bytes([255, 0, 0])


def test_qemu_screenshot_uses_a_unique_tempfile_and_cleans_up(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-screenshot-test"
    workdir.mkdir()
    fake = _register_fake_vm("screenshot-test", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _ScreendumpQMP(_ONE_PIXEL_PPM)

    try:
        image = server.qemu_screenshot(name="screenshot-test")
        assert image.data[:8] == b"\x89PNG\r\n\x1a\n"
        # Same fixed name every call would race under concurrent callers -
        # each call must get its own file, and none should be left behind.
        server.qemu_screenshot(name="screenshot-test")
        assert len(set(fake.qmp.filenames)) == 2
        assert list(workdir.glob("*.ppm")) == []
    finally:
        vm._vms.pop("screenshot-test", None)


def test_qemu_wait_screen_uses_a_unique_tempfile_and_cleans_up(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-wait-screen-test"
    workdir.mkdir()
    fake = _register_fake_vm("wait-screen-test", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _ScreendumpQMP(_ONE_PIXEL_PPM)

    try:
        result = server.qemu_wait_screen(
            name="wait-screen-test", timeout_s=5, poll_interval_s=0.01, stable_polls=2
        )
        assert result.startswith("SETTLED")
        assert len(fake.qmp.filenames) == 2
        assert fake.qmp.filenames[0] == fake.qmp.filenames[1], (
            "polls within one call may reuse a file, just not across calls/tools"
        )
        assert list(workdir.glob("*.ppm")) == []
    finally:
        vm._vms.pop("wait-screen-test", None)


class _HMPQMP(_FakeQMP):
    """human-monitor-command returns whatever text the fake HMP command prints."""

    def __init__(self, output):
        self.output = output

    def command(self, name, **kwargs):
        assert name == "human-monitor-command"
        return self.output


def test_qemu_snapshot_save_reports_success_on_empty_hmp_output(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-save-ok"
    workdir.mkdir()
    fake = _register_fake_vm("snap-save-ok", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("")

    try:
        out = server.qemu_snapshot_save(name="snap-save-ok", tag="clean-boot")
    finally:
        vm._vms.pop("snap-save-ok", None)

    assert out == "saved snapshot 'clean-boot' for VM 'snap-save-ok'"


def test_qemu_snapshot_save_surfaces_hmp_error_instead_of_claiming_success(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-save-fail"
    workdir.mkdir()
    fake = _register_fake_vm("snap-save-fail", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("Error: Device 'ide0-hd0' does not support snapshots\n")

    try:
        out = server.qemu_snapshot_save(name="snap-save-fail", tag="clean-boot")
    finally:
        vm._vms.pop("snap-save-fail", None)

    assert "may have FAILED" in out
    assert "does not support snapshots" in out


def test_qemu_snapshot_load_surfaces_hmp_error_instead_of_claiming_success(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-load-fail"
    workdir.mkdir()
    fake = _register_fake_vm("snap-load-fail", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("Error: unable to find snapshot 'missing'\n")

    try:
        out = server.qemu_snapshot_load(name="snap-load-fail", tag="missing")
    finally:
        vm._vms.pop("snap-load-fail", None)

    assert "may have FAILED" in out
    assert "unable to find snapshot" in out


def test_qemu_snapshot_load_reports_success_on_empty_hmp_output(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-load-ok"
    workdir.mkdir()
    fake = _register_fake_vm("snap-load-ok", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("")

    try:
        out = server.qemu_snapshot_load(name="snap-load-ok", tag="clean-boot")
    finally:
        vm._vms.pop("snap-load-ok", None)

    assert out == "loaded snapshot 'clean-boot' for VM 'snap-load-ok'"


def test_qemu_snapshot_delete_reports_success_on_empty_hmp_output(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-delete-ok"
    workdir.mkdir()
    fake = _register_fake_vm("snap-delete-ok", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("")

    try:
        out = server.qemu_snapshot_delete(name="snap-delete-ok", tag="clean-boot")
    finally:
        vm._vms.pop("snap-delete-ok", None)

    assert out == "deleted snapshot 'clean-boot' for VM 'snap-delete-ok'"


def test_qemu_snapshot_delete_surfaces_hmp_error_instead_of_claiming_success(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-delete-fail"
    workdir.mkdir()
    fake = _register_fake_vm("snap-delete-fail", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("Error: snapshot 'missing' not found\n")

    try:
        out = server.qemu_snapshot_delete(name="snap-delete-fail", tag="missing")
    finally:
        vm._vms.pop("snap-delete-fail", None)

    assert "may have FAILED" in out
    assert "not found" in out


def test_qemu_snapshot_list_returns_raw_hmp_output(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-list-ok"
    workdir.mkdir()
    fake = _register_fake_vm("snap-list-ok", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("Tag  VM size  Date  VM clock\nclean-boot  1G  ...\n")

    try:
        out = server.qemu_snapshot_list(name="snap-list-ok")
    finally:
        vm._vms.pop("snap-list-ok", None)

    assert out == "Tag  VM size  Date  VM clock\nclean-boot  1G  ..."


def test_qemu_snapshot_list_reports_placeholder_on_empty_hmp_output(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-snap-list-empty"
    workdir.mkdir()
    fake = _register_fake_vm("snap-list-empty", workdir)
    fake.proc = _RunningFakeProc()
    fake.qmp = _HMPQMP("")

    try:
        out = server.qemu_snapshot_list(name="snap-list-empty")
    finally:
        vm._vms.pop("snap-list-empty", None)

    assert out == "(no snapshot info returned)"


def test_qemu_serial_reads_the_tail_after_the_vm_has_exited(tmp_path):
    from qemu_mcp import server

    workdir = tmp_path / "qemu-mcp-serial-exited-test"
    workdir.mkdir()
    (workdir / "serial.log").write_text("line one\nline two\n")
    _register_fake_vm("serial-exited-test", workdir)

    try:
        out = server.qemu_serial(name="serial-exited-test")
    finally:
        vm._vms.pop("serial-exited-test", None)

    assert "VM exited, code 0" in out
    assert "line one" in out
    assert "line two" in out


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

    def __init__(self, port, connect_timeout=20.0, read_timeout=15.0):
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


class _PortConflictQMPClient:
    """Stands in for QMPClient: raises QMPError (after a short delay so the
    "QEMU exited immediately" branch's proc.poll() check is reliable) for the
    first `fail_times` construction calls, then succeeds - simulating a fake
    QEMU that loses the race for one of its ports the first few times."""

    attempts = 0
    fail_times = 0

    def __init__(self, port, connect_timeout=20.0, read_timeout=15.0):
        time.sleep(0.3)
        type(self).attempts += 1
        if type(self).attempts <= type(self).fail_times:
            raise vm.QMPError("simulated: connect refused")

    def command(self, name, **kwargs):
        return {}

    def close(self):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_retries_on_address_already_in_use_then_succeeds(tmp_path, monkeypatch):
    _make_fake_qemu_script(
        tmp_path,
        'echo "qemu-system-x86_64: -qmp tcp:127.0.0.1:0: '
        'Failed to bind socket: Address already in use" >&2\nexit 1',
    )
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    _PortConflictQMPClient.attempts = 0
    _PortConflictQMPClient.fail_times = vm._MAX_PORT_CONFLICT_RETRIES - 1
    monkeypatch.setattr(vm, "QMPClient", _PortConflictQMPClient)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        booted = vm.boot(
            name="boot-port-conflict-retry", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert booted.name == "boot-port-conflict-retry"
        assert _PortConflictQMPClient.attempts == vm._MAX_PORT_CONFLICT_RETRIES
    finally:
        vm._vms.pop("boot-port-conflict-retry", None)


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_gives_up_after_max_port_conflict_retries(tmp_path, monkeypatch):
    _make_fake_qemu_script(
        tmp_path,
        'echo "qemu-system-x86_64: -qmp tcp:127.0.0.1:0: '
        'Failed to bind socket: Address already in use" >&2\nexit 1',
    )
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    _PortConflictQMPClient.attempts = 0
    _PortConflictQMPClient.fail_times = vm._MAX_PORT_CONFLICT_RETRIES + 5
    monkeypatch.setattr(vm, "QMPClient", _PortConflictQMPClient)
    created = _track_mkdtemp(monkeypatch)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        vm.boot(
            name="boot-port-conflict-exhausted", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "Address already in use" in str(e)

    assert _PortConflictQMPClient.attempts == vm._MAX_PORT_CONFLICT_RETRIES
    assert "boot-port-conflict-exhausted" not in vm._vms
    assert created and all(not os.path.exists(d) for d in created)


class _RecordingQMPClient:
    """Stands in for QMPClient: records the timeout kwargs it was constructed
    with instead of actually connecting, so a test can assert vm.boot()
    threads qmp_connect_timeout_s/qmp_read_timeout_s through correctly."""

    calls = []

    def __init__(self, port, connect_timeout=20.0, read_timeout=15.0):
        _RecordingQMPClient.calls.append((connect_timeout, read_timeout))

    def command(self, name, **kwargs):
        return {}

    def close(self):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_passes_qmp_timeouts_through_to_qmpclient(tmp_path, monkeypatch):
    _make_fake_qemu_script(tmp_path, "exit 0")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    _RecordingQMPClient.calls = []
    monkeypatch.setattr(vm, "QMPClient", _RecordingQMPClient)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        vm.boot(
            name="boot-custom-timeouts", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
            qmp_connect_timeout_s=5.0, qmp_read_timeout_s=2.0,
        )
        assert _RecordingQMPClient.calls == [(5.0, 2.0)]
    finally:
        booted = vm._vms.pop("boot-custom-timeouts", None)
        if booted is not None:
            booted.proc.wait(timeout=3)
            shutil.rmtree(booted.workdir, ignore_errors=True)


class _SlowConnectQMPClient:
    """Stands in for QMPClient: takes a while to "connect" and records the
    monotonic time at which it finished, so a test can compare that against
    VM.started_at without needing a real QMP server socket."""

    connected_at = None

    def __init__(self, port, connect_timeout=20.0, read_timeout=15.0):
        time.sleep(0.2)
        _SlowConnectQMPClient.connected_at = time.monotonic()

    def command(self, name, **kwargs):
        return {}

    def close(self):
        pass


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_captures_started_at_after_qmp_connects_not_at_popen_time(tmp_path, monkeypatch):
    _make_fake_qemu_script(tmp_path, "exit 0")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    _SlowConnectQMPClient.connected_at = None
    monkeypatch.setattr(vm, "QMPClient", _SlowConnectQMPClient)

    real_popen = vm.subprocess.Popen
    popen_started_at = []

    def _timing_popen(*args, **kwargs):
        popen_started_at.append(time.monotonic())
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(vm.subprocess, "Popen", _timing_popen)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        booted = vm.boot(
            name="boot-started-at-timing", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert len(popen_started_at) == 1
        assert _SlowConnectQMPClient.connected_at is not None
        # started_at should track when QMP actually connected (this test's
        # fake QMPClient.__init__ sleeps 0.2s to simulate that), not the
        # moment Popen() was called - which would understate how long QEMU
        # took to become reachable over QMP.
        assert booted.started_at == pytest.approx(_SlowConnectQMPClient.connected_at, abs=0.1)
        assert booted.started_at - popen_started_at[0] >= 0.15
    finally:
        booted = vm._vms.pop("boot-started-at-timing", None)
        if booted is not None:
            booted.proc.wait(timeout=3)
            shutil.rmtree(booted.workdir, ignore_errors=True)


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_closes_its_own_handle_on_the_qemu_log_write_file(tmp_path, monkeypatch):
    _make_fake_qemu_script(tmp_path, "exit 0")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    _RecordingQMPClient.calls = []
    monkeypatch.setattr(vm, "QMPClient", _RecordingQMPClient)
    real_open = open
    opened = []

    def _tracking_open(path, *args, **kwargs):
        f = real_open(path, *args, **kwargs)
        if str(path).endswith("qemu.log"):
            opened.append(f)
        return f

    monkeypatch.setattr("builtins.open", _tracking_open)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    try:
        vm.boot(
            name="boot-log-handle", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        write_handles = [f for f in opened if "w" in f.mode]
        assert write_handles and all(f.closed for f in write_handles)
    finally:
        booted = vm._vms.pop("boot-log-handle", None)
        if booted is not None:
            booted.proc.wait(timeout=3)
            shutil.rmtree(booted.workdir, ignore_errors=True)


@pytest.mark.skipif(sys.platform == "win32", reason="fake binary is a POSIX shell script")
def test_boot_reaps_a_stale_exited_vm_registered_under_the_same_name(tmp_path, monkeypatch):
    _make_fake_qemu_script(tmp_path, "exit 0")
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(vm, "QMPClient", _RecordingQMPClient)
    iso = tmp_path / "fake.iso"
    iso.write_bytes(b"")

    stale_workdir = tmp_path / "stale-workdir"
    stale_workdir.mkdir()
    _register_fake_vm("reboot-me", stale_workdir)

    try:
        vm.boot(
            name="reboot-me", arch="x86_64", memory_mb=64,
            iso=str(iso), kernel=None, append=None, initrd=None,
            disk=None, extra_args=None,
        )
        assert not stale_workdir.exists(), "the exited entry's workdir should be reaped"
        assert vm._vms["reboot-me"].workdir != str(stale_workdir)
    finally:
        booted = vm._vms.pop("reboot-me", None)
        if booted is not None:
            booted.proc.wait(timeout=3)
            shutil.rmtree(booted.workdir, ignore_errors=True)


def test_qemu_wait_screen_rejects_non_positive_poll_interval():
    # Regression test: a non-positive poll_interval_s used to reach
    # time.sleep(poll_interval_s) unvalidated - 0 would busy-loop screendump
    # calls against the VM forever, and a negative value raised a raw
    # ValueError from time.sleep after already sending one screendump. No
    # VM needs to be registered: the check now fires before vmmod.get_vm.
    from qemu_mcp import server

    for bad in (0, -1, -0.5):
        try:
            server.qemu_wait_screen(name="no-such-vm", poll_interval_s=bad)
            assert False, f"expected ValueError for poll_interval_s={bad!r}"
        except ValueError as e:
            assert "poll_interval_s" in str(e)


def test_qemu_wait_screen_rejects_non_positive_stable_polls_before_vm_lookup():
    # stable_polls was already validated by screenmod.StabilityTracker, but
    # only after vmmod.get_vm(name) had already required a running VM to
    # exist - moved earlier as part of the poll_interval_s fix above, so a
    # bad stable_polls now fails the same way regardless of VM state.
    from qemu_mcp import server

    try:
        server.qemu_wait_screen(name="no-such-vm", stable_polls=0)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "stable_polls" in str(e)


def test_qemu_wait_serial_rejects_non_positive_poll_interval():
    # Same pattern as qemu_wait_screen's poll_interval_s check above: a
    # non-positive value used to reach the hardcoded time.sleep(0.25) call
    # (now time.sleep(poll_interval_s)) unvalidated. No VM needs to be
    # registered: the check fires before vmmod.get_vm.
    from qemu_mcp import server

    for bad in (0, -1, -0.5):
        try:
            server.qemu_wait_serial(name="no-such-vm", text="x", poll_interval_s=bad)
            assert False, f"expected ValueError for poll_interval_s={bad!r}"
        except ValueError as e:
            assert "poll_interval_s" in str(e)


def test_qemu_type_rejects_negative_delay_ms():
    # Regression test: a negative delay_ms used to reach time.sleep(delay_ms
    # / 1000) unvalidated, inside the per-character loop - so it raised a
    # raw ValueError from time.sleep only *after* one or more keystrokes had
    # already been sent to the guest, instead of failing cleanly up front.
    # No VM needs to be registered: the check now fires before vmmod.get_vm.
    from qemu_mcp import server

    for bad in (-1, -50):
        try:
            server.qemu_type(name="no-such-vm", text="hi", delay_ms=bad)
            assert False, f"expected ValueError for delay_ms={bad!r}"
        except ValueError as e:
            assert "delay_ms" in str(e)
