"""Unit tests for mouse.py's fraction -> QMP input-send-event translation.

No QEMU needed - this only checks the event lists we'd hand to QMP.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp import mouse  # noqa: E402


def test_move_events_top_left():
    assert mouse.move_events(0.0, 0.0) == [
        {"type": "abs", "data": {"axis": "x", "value": 0}},
        {"type": "abs", "data": {"axis": "y", "value": 0}},
    ]


def test_move_events_bottom_right():
    assert mouse.move_events(1.0, 1.0) == [
        {"type": "abs", "data": {"axis": "x", "value": 32767}},
        {"type": "abs", "data": {"axis": "y", "value": 32767}},
    ]


def test_move_events_scales_linearly():
    events = mouse.move_events(0.25, 0.75)
    assert events[0]["data"]["value"] == round(0.25 * 32767)
    assert events[1]["data"]["value"] == round(0.75 * 32767)


def test_move_events_rejects_out_of_range():
    for bad in (-0.1, 1.1):
        try:
            mouse.move_events(bad, 0.5)
            assert False, f"expected ValueError for x={bad}"
        except ValueError:
            pass
        try:
            mouse.move_events(0.5, bad)
            assert False, f"expected ValueError for y={bad}"
        except ValueError:
            pass


def test_click_events_appends_button_down_then_up():
    events = mouse.click_events(0.5, 0.5, "left")
    assert events[:2] == mouse.move_events(0.5, 0.5)
    assert events[2] == {"type": "btn", "data": {"down": True, "button": "left"}}
    assert events[3] == {"type": "btn", "data": {"down": False, "button": "left"}}


def test_click_events_accepts_all_named_buttons():
    for button in ("left", "right", "middle"):
        events = mouse.click_events(0.1, 0.1, button)
        assert events[2]["data"]["button"] == button


def test_click_events_rejects_unknown_button():
    try:
        mouse.click_events(0.5, 0.5, "scroll")
        assert False, "expected ValueError"
    except ValueError as e:
        assert "scroll" in str(e)
