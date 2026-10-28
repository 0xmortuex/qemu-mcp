"""Screen-fraction coordinates -> QMP `input-send-event` event lists.

QEMU's absolute pointer device reports position on a fixed 0..0x7fff axis
regardless of the guest's actual screen resolution, so callers work in
fractions of width/height (0.0..1.0) instead of pixels.
"""

from __future__ import annotations

from typing import Any

_AXIS_MAX = 32767  # 0x7fff - QEMU's absolute pointer axis range

# QEMU's QMP InputButton enum (qapi/ui.json), minus "touch" (since 8.1) -
# that one needs a tracking-id/slot event shape instead of a plain down/up
# press, so it doesn't fit click_events()'s press-then-release model below.
_BUTTONS = {
    "left",
    "right",
    "middle",
    "wheel-up",
    "wheel-down",
    "wheel-left",
    "wheel-right",
    "side",
    "extra",
}


def _axis(fraction: float, axis: str) -> dict[str, Any]:
    if not 0.0 <= fraction <= 1.0:
        raise ValueError(f"{axis} must be between 0.0 and 1.0, got {fraction!r}")
    return {"type": "abs", "data": {"axis": axis, "value": round(fraction * _AXIS_MAX)}}


def move_events(x: float, y: float) -> list[dict[str, Any]]:
    """Move the absolute pointer to (x, y), fractions of screen width/height."""
    return [_axis(x, "x"), _axis(y, "y")]


def click_events(x: float, y: float, button: str) -> list[dict[str, Any]]:
    """Move to (x, y) then press and release `button`.

    One of "left"/"right"/"middle" (the main click buttons), "wheel-up"/
    "wheel-down"/"wheel-left"/"wheel-right" (scroll a guest GUI's scrollable
    widget), or "side"/"extra" (a 5-button mouse's extra side buttons -
    needs the guest's PS/2 mouse driver in IMEX mode to see them).
    """
    if button not in _BUTTONS:
        raise ValueError(
            f"unknown mouse button {button!r} - use one of {sorted(_BUTTONS)}"
        )
    return [
        *move_events(x, y),
        {"type": "btn", "data": {"down": True, "button": button}},
        {"type": "btn", "data": {"down": False, "button": button}},
    ]
