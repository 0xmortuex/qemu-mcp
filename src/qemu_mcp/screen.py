"""Framebuffer-settle detection for qemu_wait_screen.

A text-mode VGA console never produces two identical screendumps while the
hardware cursor blinks (about 18 pixels flip every half second), so
"settled" means: no more than `max_changed_pixels` differ between
consecutive frames, for `stable_polls` polls in a row. Boot activity changes
hundreds of pixels per frame, so a small threshold separates the two.
"""

from __future__ import annotations

import hashlib

from PIL import Image, ImageChops


def hash_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_frame(path: str) -> Image.Image:
    with Image.open(path) as im:
        return im.convert("RGB")


def changed_pixels(a: Image.Image, b: Image.Image) -> int:
    """Number of pixels that differ; a resolution change counts as all."""
    if a.size != b.size:
        return max(a.size[0] * a.size[1], b.size[0] * b.size[1])
    diff = ImageChops.difference(a, b).convert("L")
    return diff.width * diff.height - diff.histogram()[0]


class StabilityTracker:
    """Counts consecutive frames whose change from the previous frame is at
    most `max_changed_pixels`."""

    def __init__(self, stable_polls: int, max_changed_pixels: int = 0):
        if stable_polls < 1:
            raise ValueError(f"stable_polls must be >= 1, got {stable_polls}")
        if max_changed_pixels < 0:
            raise ValueError(f"max_changed_pixels must be >= 0, got {max_changed_pixels}")
        self.stable_polls = stable_polls
        self.max_changed_pixels = max_changed_pixels
        self._prev: Image.Image | None = None
        self._count = 0
        self.last_changed: int | None = None

    def update(self, frame: Image.Image) -> bool:
        """Feed the latest frame; return True once `stable_polls` consecutive
        frames (including this one) were each within the threshold."""
        if self._prev is None:
            self._count = 1
            self.last_changed = None
        else:
            self.last_changed = changed_pixels(self._prev, frame)
            within = self.last_changed <= self.max_changed_pixels
            self._count = self._count + 1 if within else 1
        self._prev = frame
        return self._count >= self.stable_polls
