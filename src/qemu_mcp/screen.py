"""Framebuffer-settle detection for qemu_wait_screen.

QMP's screendump writes a deterministic PPM - an unchanged framebuffer
produces byte-identical files - so hashing the file is enough to detect a
settled display without decoding pixels.
"""

from __future__ import annotations

import hashlib


def hash_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class StabilityTracker:
    """Counts consecutive identical hashes fed via `update`."""

    def __init__(self, stable_polls: int):
        if stable_polls < 1:
            raise ValueError(f"stable_polls must be >= 1, got {stable_polls}")
        self.stable_polls = stable_polls
        self._prev: str | None = None
        self._count = 0

    def update(self, current_hash: str) -> bool:
        """Feed the latest hash; return True once `stable_polls` consecutive
        identical hashes (including this one) have been seen."""
        self._count = self._count + 1 if current_hash == self._prev else 1
        self._prev = current_hash
        return self._count >= self.stable_polls
