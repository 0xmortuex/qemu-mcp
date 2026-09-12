# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project has not yet made a versioned release, so everything so far is
listed under [Unreleased]; see `BACKLOG.md` for verification detail (what
was tested, what still needs a real QEMU boot) behind each entry.

## [Unreleased]

### Added
- `qemu_boot`, `qemu_stop`, `qemu_list`, `qemu_qmp` — boot, stop, list, and
  send raw QMP commands to named VMs.
- `qemu_key` / `qemu_type` — send key combos and type strings into a guest.
- `qemu_screenshot` / `qemu_serial` / `qemu_wait_serial` — capture the
  display and read/wait on the serial console log.
- `machine` parameter on `qemu_boot`, for non-x86 targets that need
  `-M virt` (aarch64, riscv64).
- `qemu_mouse` — absolute pointer move and click via QMP `input-send-event`.
- `qemu_snapshot_save` / `qemu_snapshot_load` — qcow2 VM snapshots via HMP
  `savevm`/`loadvm`, with disk format auto-detected instead of assuming raw.
- `qemu_wait_screen` — poll screendumps until the framebuffer stops
  changing, for boot-settled detection on VGA-only guests.
- `qemu_serial_send` — write to a guest's serial console over a
  bidirectional chardev socket (the serial log file is still kept).
- `qemu_snapshot_list` / `qemu_snapshot_delete` — list and remove qcow2
  snapshot tags via HMP `info snapshots` / `delvm`.
- `qemu_version` — report the installed QEMU's `--version` for a given
  arch, without booting a VM.
- `arch` and `machine` shown per-VM in `qemu_list` output.
- Overridable QMP connect/read timeouts (`qmp_connect_timeout_s`,
  `qmp_read_timeout_s`) on `qemu_boot`.
- `poll_interval_s` parameter on `qemu_wait_serial` (already present on
  `qemu_wait_screen`).
- A `"--"` escape in `qemu_key` combo syntax to send a literal `-`.

### Fixed
- `qemu_boot`'s `disk` param was hardcoded to raw format, silently
  corrupting qcow2 disks passed to it; format is now auto-detected.
- VM temp workdirs (serial log, screendump/snapshot scratch files) leaked
  on every stop and on failed boots; both paths now clean up.
- Dead VM registry entries (guest crash, external `quit`) stayed listed
  forever with their workdir never reclaimed; they're now reaped.
- `qemu_serial` required a running VM, so it couldn't be used right after
  the crash it was meant to diagnose; it now reads the log for exited VMs
  too, noting the exit code.
- QMP socket `recv`/`send` failures (timeout, broken pipe) surfaced as raw
  `TimeoutError`/`OSError` instead of the module's own `QMPError`.
- Serial console reconnect-after-drop had no handling for the reconnect
  itself failing, and left a stale socket for the next call to hit first;
  both now raise a clear `SerialError` and reset cleanly.
- `qemu_snapshot_save`/`qemu_snapshot_load` always reported success even
  when QEMU's HMP output indicated the snapshot didn't actually happen.
- `qemu_screenshot`/`qemu_wait_screen` shared a fixed per-VM filename,
  risking a read/write race between concurrent calls; each call now gets
  its own temp file, cleaned up afterward.
- `qemu_stop` waited out the full graceful-shutdown timeout even when the
  `system_powerdown` QMP command itself had failed to send.
- `vm.boot()` leaked one open file descriptor per successful boot (the
  parent's own handle to the QEMU log file was never closed).
- `vm.boot()` could hand two concurrent boots the same ephemeral port; it
  now retries with fresh ports on an address-already-in-use failure.
- `find_qemu`'s Windows fallback missed QEMU installs nested one directory
  level down (e.g. a version-named folder), a common manual-extract layout.
- Input validation added ahead of any side effects, so bad input fails
  clean instead of after a workdir/process is already created: invalid VM
  `name`s (path separators, empty, `.`/`..`); non-positive `memory_mb`;
  non-positive QMP/`qemu_wait_screen`/`qemu_wait_serial` timeouts and poll
  intervals; malformed `extra_args` shell quoting; `extra_args` flags that
  collide with flags `qemu_boot` already sets; negative `qemu_type`
  `delay_ms`; `char_to_keys` silently accepting multi-character strings.

### Changed
- Migrated from `FastMCP` to the `mcp` 2.0 `MCPServer` API and dropped the
  temporary `mcp<2.0.0` pin put in place when 2.0 first broke the import.
- CI now runs ruff, `mypy --strict`, the unit tests, and a real stdio MCP
  handshake on ubuntu/windows/macos across Python 3.10-3.13, with
  Dependabot watching both the `pip` and `github-actions` ecosystems.
- Added a PyPI trusted-publishing (OIDC) release workflow and verified
  `python -m build`/`twine check` output; the package is not yet published.
