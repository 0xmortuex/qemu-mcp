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


def test_stability_tracker_settles_after_n_identical_updates():
    tracker = screen.StabilityTracker(stable_polls=3)
    assert tracker.update("x") is False  # 1st
    assert tracker.update("x") is False  # 2nd
    assert tracker.update("x") is True  # 3rd - settled


def test_stability_tracker_resets_on_change():
    tracker = screen.StabilityTracker(stable_polls=2)
    assert tracker.update("x") is False
    assert tracker.update("y") is False  # changed, count resets to 1
    assert tracker.update("y") is True  # 2nd identical in a row


def test_stability_tracker_stable_polls_of_one_settles_immediately():
    tracker = screen.StabilityTracker(stable_polls=1)
    assert tracker.update("anything") is True
