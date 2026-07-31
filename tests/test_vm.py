"""Unit tests for vm.find_qemu's missing-binary error and vm.disk_format. No QEMU needed."""

import os
import stat
import sys

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
