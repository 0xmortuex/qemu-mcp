"""Screen-fraction coordinates -> QMP `input-send-event` event lists.

QEMU's absolute pointer device reports position on a fixed 0..0x7fff axis
regardless of the guest's actual screen resolution, so callers work in
fractions of width/height (0.0..1.0) instead of pixels.
"""

from __future__ import annotations

_AXIS_MAX = 32767  # 0x7fff - QEMU's absolute pointer axis range

_BUTTONS = {"left", "right", "middle"}


def _axis(fraction: float, axis: str) -> dict:
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"{axis} must be between 0.0 and 1.0, got {fraction!r}")
    return {"type": "abs", "data": {"axis": axis, "value": round(fraction * _AXIS_MAX)}}


def move_events(x: float, y: float) -> list[dict]:
    """Move the absolute pointer to (x, y), fractions of screen width/height."""
    return [_axis(x, "x"), _axis(y, "y")]


def click_events(x: float, y: float, button: str) -> list[dict]:
    """Move to (x, y) then press and release `button` ("left"/"right"/"middle")."""
    if button not in _BUTTONS:
        raise ValueError(f"unknown mouse button {button!r} - use left, right, or middle")
    return [
        *move_events(x, y),
        {"type": "btn", "data": {"down": True, "button": button}},
        {"type": "btn", "data": {"down": False, "button": button}},
    ]
