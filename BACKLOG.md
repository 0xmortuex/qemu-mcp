# Backlog

Real, finishable improvements — the daily agent picks ONE and ships it end-to-end.
Rules: check items off when done, add follow-ups you discover, never do two at once,
smallest-reviewable-change wins.

## Features
- [ ] `qemu_mouse` tool — QMP `input-send-event` absolute pointer move + click (guests with mouse support become fully drivable)
- [ ] Bidirectional serial: switch `-serial file:` to a chardev socket so a new `qemu_serial_send` tool can write to the guest console; keep the file log
- [ ] Snapshot tools — `qemu_snapshot_save` / `qemu_snapshot_load` (QMP savevm/loadvm; document the qcow2 requirement)
- [ ] `machine` parameter on `qemu_boot` (aarch64/riscv64 need `-M virt`; document per-arch examples in README)
- [ ] `qemu_wait_screen` — poll screendumps until the framebuffer stops changing (boot-settled detection for VGA-only guests)

## Quality
- [x] Unit tests for `keys.py` (`char_to_keys` full printable-ASCII round-trip, `parse_combo` good + error cases) — no QEMU needed, plain pytest (`tests/test_keys.py`, 168 cases; `pytest>=7` added as the `test` extra)
- [x] GitHub Actions CI: ruff + the pytest unit tests + `mcp_handshake`-style stdio smoke on ubuntu-latest and windows-latest (handshake needs no QEMU) — `.github/workflows/ci.yml` runs `ruff check` plus `tests/test_keys.py`, `tests/test_vm.py`, and the new `tests/test_stdio_handshake.py` (spawns the real server over stdio, initializes an MCP `ClientSession`, asserts the expected tool names come back) on ubuntu-latest and windows-latest with Python 3.12. Took 3 pushes to actually go green on GitHub: (1) `pip install ruff` floated to 0.16.0, whose wider default ruleset broke both OSes - fixed by pinning `ruff==0.16.0` and adding an explicit `[tool.ruff.lint] select` in `pyproject.toml` so this can't silently drift again; (2) that surfaced a real, pre-existing Windows bug in `tests/test_vm.py`'s `_make_fake_binary` - `shutil.which()` only recognizes `PATHEXT`-suffixed files on Windows, so the extension-less fake binary was invisible to `find_qemu`'s exact-match path even though `_installed_arches`' directory scan found it fine. Fixed by giving the helper a `.exe` suffix on `win32`, matching a real QEMU install; (3) that in turn exposed `shutil.which()` returning the `PATHEXT` suffix in a different case (`.EXE`) than the file we created (`.exe`) - same file on Windows' case-insensitive filesystem, but a strict string `==` failed. Fixed by comparing with `os.path.normcase()`. Verified locally (Linux, where normcase is a no-op); watching run 30274347547's successor on GitHub to confirm windows-latest actually goes green.
- [ ] Type-check pass (`mypy --strict src/`) and fix what it finds
- [x] Better error when an arch binary is missing: list which qemu-system-* binaries WERE found — `find_qemu` now scans PATH (and the Windows QEMU dirs) for other `qemu-system-*` binaries and includes them in the `FileNotFoundError`, so picking a wrong `arch` tells you what's actually installed instead of just "not found". Verified with `tests/test_vm.py` (fake binaries on a scratch `PATH`, no real QEMU needed): lists other installed arches, reports none-found, still returns the exact match when present.
- [x] `char_to_keys` silently accepted multi-char strings (`str.islower()`/`isdigit()`/`isupper()` match whole strings, not just one char) and returned a nonsense key combo instead of raising — added a `len(ch) != 1` guard at the top; `test_char_to_keys_does_not_validate_length` flipped to `test_char_to_keys_rejects_non_single_char` (asserts `ValueError` for `"ab"`, `"AB"`, `""`, `"abc"`). Verified: `char_to_keys` is only ever called with single characters (`qemu_type`'s `for ch in text`, `parse_combo`'s `len(p) == 1` branch), so no caller behavior changes.

## Distribution
- [ ] PyPI packaging: verify `python -m build` output, add publish workflow (trusted publishing), reserve the name
- [ ] README: terminal-cast GIF of a full boot-type-screenshot loop
