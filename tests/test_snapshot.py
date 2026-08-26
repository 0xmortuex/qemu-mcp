"""Unit tests for snapshot tag validation and HMP command-line building.

No QEMU needed - pure string handling.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp import snapshot  # noqa: E402


@pytest.mark.parametrize("tag", ["clean-boot", "pre_update", "v1.2", "A9", "a"])
def test_validate_tag_accepts_plain_identifiers(tag):
    assert snapshot.validate_tag(tag) == tag


@pytest.mark.parametrize(
    "tag",
    ["", "with space", "semi;colon", "quote'd", 'quote"d', "a/b", "$(rm -rf /)", "a\nb"],
)
def test_validate_tag_rejects_anything_else(tag):
    with pytest.raises(ValueError):
        snapshot.validate_tag(tag)


def test_save_command_line():
    assert snapshot.save_command_line("clean-boot") == "savevm clean-boot"


def test_load_command_line():
    assert snapshot.load_command_line("clean-boot") == "loadvm clean-boot"


def test_save_command_line_rejects_invalid_tag():
    with pytest.raises(ValueError):
        snapshot.save_command_line("with space")


def test_load_command_line_rejects_invalid_tag():
    with pytest.raises(ValueError):
        snapshot.load_command_line("with space")


def test_delete_command_line():
    assert snapshot.delete_command_line("clean-boot") == "delvm clean-boot"


def test_delete_command_line_rejects_invalid_tag():
    with pytest.raises(ValueError):
        snapshot.delete_command_line("with space")


def test_list_command_line():
    assert snapshot.list_command_line() == "info snapshots"
