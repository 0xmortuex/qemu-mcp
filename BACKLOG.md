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
- [ ] GitHub Actions CI: ruff + the pytest unit tests + `mcp_handshake`-style stdio smoke on ubuntu-latest and windows-latest (handshake needs no QEMU)
- [ ] Type-check pass (`mypy --strict src/`) and fix what it finds
- [ ] Better error when an arch binary is missing: list which qemu-system-* binaries WERE found
- [ ] `char_to_keys` silently accepts multi-char strings (`str.islower()`/`isdigit()`/`isupper()` match whole strings, not just one char) and returns a nonsense key combo instead of raising — add a `len(ch) != 1` guard at the top; pinned by `test_char_to_keys_does_not_validate_length` in `tests/test_keys.py`, which documents current (wrong) behavior so it can be flipped to an assert-raises once fixed

## Distribution
- [ ] PyPI packaging: verify `python -m build` output, add publish workflow (trusted publishing), reserve the name
- [ ] README: terminal-cast GIF of a full boot-type-screenshot loop
