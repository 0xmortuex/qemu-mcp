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
- `accel` parameter on `qemu_boot`, to opt into hardware acceleration
  (`-accel kvm`/`hvf`/`whpx`, with a `:tcg` fallback) instead of the
  software-only TCG default.
- `cpu` parameter on `qemu_boot`, to select or customize the emulated CPU
  model (`-cpu qemu64,+avx`/`max`/`host`...) instead of QEMU's per-arch
  default.
- `graceful_timeout_s` / `kill_timeout_s` parameters on `qemu_stop`, to
  override the previously-hardcoded ~10s ACPI-shutdown wait and 3s
  post-`quit` process-exit wait.
- MCP tool annotations on every tool: `readOnlyHint`, `destructiveHint`,
  `idempotentHint` and `openWorldHint`, all stated explicitly, so clients
  can tell which calls to confirm with the user. `tests/test_tool_hints.py`
  pins every value.
- `smp_cores` / `smp_threads` / `smp_sockets` / `smp_maxcpus` parameters on
  `qemu_boot`, combined onto the same `-smp` flag as `smp` (e.g.
  `-smp 8,cores=4,threads=2,sockets=1`), for shaping a guest's CPU topology
  rather than just its total vCPU count.
- `hostfwd` parameter on `qemu_boot` (e.g. `"tcp::2222-:22"`), a convenience
  that builds the `-netdev user,id=net0,hostfwd=...` / `-device
  e1000,netdev=net0` pair for reaching a guest service (SSH, a web server
  under test) from the host, instead of needing QEMU's own NIC/chipset flags.
- `qemu_mouse`'s `button` now also accepts `wheel-up`/`wheel-down`/
  `wheel-left`/`wheel-right` (scroll a widget under the pointer) and
  `side`/`extra` (a 5-button mouse's extra buttons), not just
  `left`/`right`/`middle`.
- `qemu_key` now accepts `sysrq` as a key name, to send the Linux Magic
  SysRq key (e.g. `alt-sysrq-s`/`alt-sysrq-c` to sync disks or force a
  crash dump on a guest kernel built with `CONFIG_MAGIC_SYSRQ`).

### Changed
- `qemu_wait_serial` now searches only output after the previous successful wait's match
  (per VM), so waiting for a prompt after typing a command finds the new prompt instead
  of returning instantly on the old one. The first wait still searches from the start of
  the log; `from_start=True` restores the whole-log search.
- `qemu_wait_screen` settles when consecutive frames differ by at most
  `max_changed_pixels` (default 64) instead of requiring byte-identical frames: a
  blinking text-mode cursor flips ~18 pixels forever, so text consoles never settled.
- Migrated from `FastMCP` to the `mcp` 2.0 `MCPServer` API and dropped the
  temporary `mcp<2.0.0` pin put in place when 2.0 first broke the import.
- CI now runs ruff, `mypy --strict`, the unit tests, and a real stdio MCP
  handshake on ubuntu/windows/macos across Python 3.10-3.13, with
  Dependabot watching both the `pip` and `github-actions` ecosystems.
- Added a PyPI trusted-publishing (OIDC) release workflow and verified
  `python -m build`/`twine check` output; the package is not yet published.
- Added a `py.typed` marker (PEP 561) so type checkers recognize that
  `qemu_mcp` ships inline types, instead of treating it as untyped.

### Fixed
- `qemu_type` translated characters while sending, so an untypeable character left a
  partial string in the guest; the whole string is now validated first.
- On Windows, QEMU closing its QMP socket surfaced as `QMP connection error: [WinError
  10053] ...` instead of `QMP connection closed by QEMU`; connection aborts/resets are
  now reported as a close on every OS. Two tests were also made OS-independent (a TCP
  read that assumed both sends arrive together; a serial log written in text mode).
- Tool errors now reach the agent. mcp 2's `MCPServer` replaces any exception
  that isn't a `ToolError` with a bare "Error executing tool X", so every
  instructive message (`no VM named ...`, `VM has exited. Last serial output: ...`,
  `qemu-system-foo not found. Found on this system: ...`) was invisible to the
  agent. Expected failures are now re-raised as `ToolError` at the tool boundary;
  a new stdio test asserts the text arrives.
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
- `qemu_wait_serial`/`qemu_wait_screen` with `timeout_s<=0` skipped their
  check/poll loop entirely and reported `TIMEOUT` unconditionally, even
  when the text was already present or the display had already settled;
  both now always check at least once regardless of `timeout_s`.
- `vm.boot()` leaked one open file descriptor per successful boot (the
  parent's own handle to the QEMU log file was never closed).
- `vm.boot()` could hand two concurrent boots the same ephemeral port; it
  now retries with fresh ports on an address-already-in-use failure.
- `find_qemu`'s Windows fallback missed QEMU installs nested one directory
  level down (e.g. a version-named folder), a common manual-extract layout.
- `QMPClient.command()` and `SerialConsole.send()` shared one socket across
  concurrent tool calls against the same VM with no lock; two calls could
  cross-talk (reading each other's QMP reply) or race on the serial
  socket's own state. Both now hold a lock for the whole round trip.
- `qemu_wait_serial` re-read and re-decoded the entire serial log on every
  poll; it now tracks a byte offset and only reads what's new since the
  last poll, so a long wait against a chatty guest doesn't get slower
  per-poll as the log grows.
- Input validation added ahead of any side effects, so bad input fails
  clean instead of after a workdir/process is already created: invalid VM
  `name`s (path separators, empty, `.`/`..`); invalid `arch` values on
  `qemu_boot`/`qemu_version` (same path-separator/empty/`.`/`..` check as
  `name`, since `find_qemu` interpolates `arch` into a binary name looked
  up via `shutil.which`); non-positive `memory_mb`; non-positive
  QMP/`qemu_wait_screen`/`qemu_wait_serial` timeouts and poll intervals;
  malformed `extra_args` shell quoting; `extra_args` flags that collide
  with flags `qemu_boot` already sets; negative `qemu_type` `delay_ms`;
  `char_to_keys` silently accepting multi-character strings.
- `qemu_stop` could close a VM's QMP/serial connections and remove its temp
  directory while a concurrent `qemu_wait_serial`/`qemu_wait_screen`/
  `qemu_screenshot` call was still polling it, surfacing a confusing error
  instead of that call's own clean result; `qemu_stop` now waits briefly
  for any such in-flight call to finish first.
- `vm.py` raised a `DeprecationWarning: invalid escape sequence '\q'` on
  every import, from an unescaped `\q` in a non-raw docstring.
- `qemu_wait_serial(text="")` reported `FOUND` on its very first poll
  regardless of the VM's actual serial output, since an empty search
  string always matches at position 0; `text` is now required to be
  non-empty.
- `QMPClient.close()`/`SerialConsole.close()` could null out the socket
  while a `command()`/`send()` call was still in flight on another thread,
  turning a clean `QMPError`/`SerialError` into a raw `AttributeError`;
  both `close()` methods now hold the same lock the round trip does.
- `vm.version()` let a hung/killed `qemu-system-* --version` raise a raw
  `subprocess.TimeoutExpired` instead of the module's own clear error.
- `vm.stop()`'s kill-timeout branch killed the process but never reaped it
  afterward, unlike the equivalent `vm.boot()` failure path.
- `SerialConsole.send()`'s reconnect-after-drop path leaked the freshly
  opened socket if the resend on it also failed.
- `qemu_serial_send`/`qemu_qmp` didn't mark themselves in-use the way
  `qemu_wait_serial`/`qemu_wait_screen`/`qemu_screenshot` already did, so a
  concurrent `qemu_stop` could close their connection out from under them.
- `reap_dead()` (called from `qemu_list` and `qemu_boot`) closed a dead
  VM's connections and removed its workdir with no wait at all for an
  in-flight caller, unlike `qemu_stop`'s own brief wait; it now waits the
  same way.
- `SerialConsole.send()`'s reconnect path closed the dead socket without
  guarding against `close()` itself raising `OSError`, which could escape
  uncaught and skip clearing the stale socket reference for the next call.
