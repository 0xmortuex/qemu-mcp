"""Unit tests for screen.py's framebuffer-settle detection.

No QEMU needed - hash_file only reads plain files, and StabilityTracker
only counts hashes fed to it.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp import screen  # noqa: E402


def test_hash_file_same_content_same_hash(tmp_path):
    a = tmp_path / "a.ppm"
    b = tmp_path / "b.ppm"
    a.write_bytes(b"same frame")
    b.write_bytes(b"same frame")
    assert screen.hash_file(str(a)) == screen.hash_file(str(b))


def test_hash_file_different_content_different_hash(tmp_path):
    a = tmp_path / "a.ppm"
    b = tmp_path / "b.ppm"
    a.write_bytes(b"frame one")
    b.write_bytes(b"frame two")
    assert screen.hash_file(str(a)) != screen.hash_file(str(b))


def test_stability_tracker_rejects_non_positive_stable_polls():
    with pytest.raises(ValueError):
        screen.StabilityTracker(0)
    with pytest.raises(ValueError):
        screen.StabilityTracker(-1)


def _frame(changed=0, size=(64, 32)):
    """A black frame with `changed` white pixels in the top row(s)."""
    from PIL import Image
    im = Image.new("RGB", size)
    for i in range(changed):
        im.putpixel((i % size[0], i // size[0]), (255, 255, 255))
    return im


def test_changed_pixels_counts_differences():
    assert screen.changed_pixels(_frame(0), _frame(0)) == 0
    assert screen.changed_pixels(_frame(0), _frame(18)) == 18
    assert screen.changed_pixels(_frame(0), _frame(0, size=(32, 32))) == 64 * 32


def test_stability_tracker_settles_after_n_identical_updates():
    tracker = screen.StabilityTracker(stable_polls=3)
    assert tracker.update(_frame(0)) is False  # 1st
    assert tracker.update(_frame(0)) is False  # 2nd
    assert tracker.update(_frame(0)) is True  # 3rd - settled


def test_stability_tracker_resets_on_change():
    tracker = screen.StabilityTracker(stable_polls=2)
    assert tracker.update(_frame(0)) is False
    assert tracker.update(_frame(200)) is False  # changed, count resets to 1
    assert tracker.update(_frame(200)) is True  # 2nd identical in a row


def test_stability_tracker_stable_polls_of_one_settles_immediately():
    tracker = screen.StabilityTracker(stable_polls=1)
    assert tracker.update(_frame(5)) is True


def test_blinking_cursor_counts_as_settled_within_threshold():
    """A text-mode cursor flips ~18 pixels every frame forever; with a
    byte-identical rule qemu_wait_screen never settled on a text console."""
    strict = screen.StabilityTracker(stable_polls=3, max_changed_pixels=0)
    tolerant = screen.StabilityTracker(stable_polls=3, max_changed_pixels=64)
    frames = [_frame(0), _frame(18), _frame(0), _frame(18)]
    assert not any(strict.update(f) for f in frames)
    assert [tolerant.update(f) for f in frames] == [False, False, True, True]
    assert tolerant.last_changed == 18


def test_boot_activity_exceeds_threshold():
    tracker = screen.StabilityTracker(stable_polls=2, max_changed_pixels=64)
    assert tracker.update(_frame(0)) is False
    assert tracker.update(_frame(400)) is False  # hundreds of pixels: still booting
    assert tracker.last_changed == 400


def test_stability_tracker_rejects_negative_threshold():
    with pytest.raises(ValueError):
        screen.StabilityTracker(1, max_changed_pixels=-1)
