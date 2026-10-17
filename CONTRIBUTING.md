# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # .venv\Scripts\activate on Windows
pip install "ruff==0.16.0" "mypy==2.3.0" -e ".[test]"
```

Pinned `ruff`/`mypy` versions match what CI installs
(`.github/workflows/ci.yml`) — an unpinned `pip install ruff` can resolve to
a newer release with a different default ruleset and fail locally in ways
CI doesn't, or vice versa.

## Checks

Run these before opening a PR — they're exactly what CI runs on every push,
across a 3-OS / 4-Python-version matrix (`ubuntu-latest` on 3.10-3.13,
`windows-latest`/`macos-latest` on 3.12):

```bash
ruff check src tests
mypy --strict src
pytest tests/test_keys.py tests/test_mouse.py tests/test_screen.py tests/test_snapshot.py tests/test_serial.py tests/test_qmp.py tests/test_vm.py tests/test_stdio_handshake.py tests/test_tool_hints.py tests/test_version.py
```

None of this needs a QEMU install — these tests use fake QEMU
binaries/QMP servers, or (for the stdio handshake) spawn the real server
over stdio without booting a VM. The only thing that does need QEMU is
`tests/smoke_test.py`, a separate end-to-end script (see the README's
[Tests](README.md#tests) section) that isn't run by CI and isn't required
for a PR.

## Before committing

- `python -m compileall src` — fast sanity check that every module still
  imports cleanly.
- If you touched a tool's behavior, update its docstring and the README's
  tools table.
- If you found further work while in there, add it to `BACKLOG.md` rather
  than letting it go unrecorded.
