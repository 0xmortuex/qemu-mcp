"""Unit tests for keys.py - char_to_keys and parse_combo. No QEMU needed."""

import os
import string
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qemu_mcp.keys import char_to_keys, parse_combo  # noqa: E402

# string.printable minus the two control chars keys.py has no mapping for
SUPPORTED_PRINTABLE = "".join(c for c in string.printable if c not in "\x0b\x0c")


@pytest.mark.parametrize("ch", list(SUPPORTED_PRINTABLE))
def test_char_to_keys_covers_all_supported_printable_ascii(ch):
    keys = char_to_keys(ch)
    assert isinstance(keys, list)
    assert keys, f"{ch!r} produced an empty key list"
    assert all(isinstance(k, str) and k for k in keys)


@pytest.mark.parametrize("ch", ["\x0b", "\x0c"])
def test_char_to_keys_rejects_unmapped_control_chars(ch):
    with pytest.raises(ValueError):
        char_to_keys(ch)


@pytest.mark.parametrize(
    "ch,expected",
    [
        ("a", ["a"]),
        ("z", ["z"]),
        ("0", ["0"]),
        ("9", ["9"]),
        ("A", ["shift", "a"]),
        ("Z", ["shift", "z"]),
        (" ", ["spc"]),
        ("\n", ["ret"]),
        ("\t", ["tab"]),
        ("\r", ["ret"]),
        ("-", ["minus"]),
        ("=", ["equal"]),
        ("[", ["bracket_left"]),
        ("]", ["bracket_right"]),
        (";", ["semicolon"]),
        ("'", ["apostrophe"]),
        ("`", ["grave_accent"]),
        ("\\", ["backslash"]),
        (",", ["comma"]),
        (".", ["dot"]),
        ("/", ["slash"]),
        ("!", ["shift", "1"]),
        ("@", ["shift", "2"]),
        ("#", ["shift", "3"]),
        ("$", ["shift", "4"]),
        ("%", ["shift", "5"]),
        ("^", ["shift", "6"]),
        ("&", ["shift", "7"]),
        ("*", ["shift", "8"]),
        ("(", ["shift", "9"]),
        (")", ["shift", "0"]),
        ("_", ["shift", "minus"]),
        ("+", ["shift", "equal"]),
        ("{", ["shift", "bracket_left"]),
        ("}", ["shift", "bracket_right"]),
        (":", ["shift", "semicolon"]),
        ('"', ["shift", "apostrophe"]),
        ("~", ["shift", "grave_accent"]),
        ("|", ["shift", "backslash"]),
        ("<", ["shift", "comma"]),
        (">", ["shift", "dot"]),
        ("?", ["shift", "slash"]),
    ],
)
def test_char_to_keys_exact_mapping(ch, expected):
    assert char_to_keys(ch) == expected


def test_char_to_keys_rejects_non_ascii():
    with pytest.raises(ValueError):
        char_to_keys("é")


@pytest.mark.parametrize("ch", ["ab", "AB", "", "abc"])
def test_char_to_keys_rejects_non_single_char(ch):
    # char_to_keys is documented as taking a single character. The
    # lower/digit/upper branches use str.islower()/isdigit()/isupper(),
    # which also match multi-char strings, so a length guard is needed
    # up front to reject anything that isn't exactly one character.
    with pytest.raises(ValueError):
        char_to_keys(ch)


@pytest.mark.parametrize(
    "combo,expected",
    [
        ("enter", ["ret"]),
        ("return", ["ret"]),
        ("ret", ["ret"]),
        ("esc", ["esc"]),
        ("escape", ["esc"]),
        ("F12", ["f12"]),
        ("f1", ["f1"]),
        ("ctrl-alt-f2", ["ctrl", "alt", "f2"]),
        ("CTRL-ALT-DELETE", ["ctrl", "alt", "delete"]),
        ("shift-a", ["shift", "a"]),
        ("a", ["a"]),
        ("A", ["a"]),  # combo parts are lowercased before lookup
        ("win", ["meta_l"]),
        ("super", ["meta_l"]),
        ("pageup", ["pgup"]),
        ("pagedown", ["pgdn"]),
        (" ctrl-c ", ["ctrl", "c"]),  # surrounding whitespace stripped
        ("--", ["minus"]),  # "--" is an escaped literal "-" key
        ("ctrl--", ["ctrl", "minus"]),  # ctrl + literal "-" (e.g. zoom out)
        ("ctrl---alt", ["ctrl", "minus", "alt"]),  # literal "-" mid-combo
        ("shift---", ["shift", "minus"]),  # trailing lone "-" is ignored
    ],
)
def test_parse_combo_good_cases(combo, expected):
    assert parse_combo(combo) == expected


@pytest.mark.parametrize("combo", ["", "   ", "-"])
def test_parse_combo_empty_combo_raises(combo):
    with pytest.raises(ValueError):
        parse_combo(combo)


@pytest.mark.parametrize("combo", ["ctrl-foobar", "ctrl-alt-notakey", "xyz"])
def test_parse_combo_unknown_key_raises(combo):
    with pytest.raises(ValueError):
        parse_combo(combo)
