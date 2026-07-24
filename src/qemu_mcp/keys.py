"""Character / key-name -> QMP qcode translation.

QMP's `send-key` takes qcodes (QKeyCode names). Typing text means
mapping each character to its base key plus shift when needed; key
combos like "ctrl-alt-f1" map each part to a qcode and press them
together.
"""

from __future__ import annotations

# char -> single unshifted qcode
_PLAIN = {
    " ": "spc", "\n": "ret", "\t": "tab",
    "-": "minus", "=": "equal", "[": "bracket_left", "]": "bracket_right",
    ";": "semicolon", "'": "apostrophe", "`": "grave_accent",
    "\\": "backslash", ",": "comma", ".": "dot", "/": "slash",
}

# shifted char -> qcode of the unshifted key
_SHIFTED = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "minus", "+": "equal", "{": "bracket_left", "}": "bracket_right",
    ":": "semicolon", '"': "apostrophe", "~": "grave_accent",
    "|": "backslash", "<": "comma", ">": "dot", "?": "slash",
}

# friendly names accepted in combos -> qcode
_NAMED = {
    "enter": "ret", "return": "ret", "ret": "ret",
    "esc": "esc", "escape": "esc",
    "backspace": "backspace", "tab": "tab", "space": "spc",
    "up": "up", "down": "down", "left": "left", "right": "right",
    "delete": "delete", "del": "delete", "insert": "insert",
    "home": "home", "end": "end", "pgup": "pgup", "pgdn": "pgdn",
    "pageup": "pgup", "pagedown": "pgdn",
    "ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift",
    "meta": "meta_l", "win": "meta_l", "super": "meta_l",
    "capslock": "caps_lock", "menu": "menu", "prtsc": "print",
}
_NAMED.update({f"f{i}": f"f{i}" for i in range(1, 13)})


def char_to_keys(ch: str) -> list[str]:
    """One character -> the qcodes to press simultaneously."""
    if ch.isascii() and (ch.islower() or ch.isdigit()):
        return [ch]
    if ch.isascii() and ch.isupper():
        return ["shift", ch.lower()]
    if ch in _PLAIN:
        return [_PLAIN[ch]]
    if ch in _SHIFTED:
        return ["shift", _SHIFTED[ch]]
    if ch == "\r":
        return ["ret"]
    raise ValueError(f"cannot type character {ch!r} (no qcode mapping)")


def parse_combo(combo: str) -> list[str]:
    """'ctrl-alt-f2' / 'F12' / 'enter' -> qcodes pressed together."""
    parts = [p for p in combo.strip().lower().split("-") if p]
    if not parts:
        raise ValueError("empty key combo")
    out = []
    for p in parts:
        if p in _NAMED:
            out.append(_NAMED[p])
        elif len(p) == 1:
            out.extend(char_to_keys(p))
        else:
            raise ValueError(
                f"unknown key {p!r} - use names like enter, esc, f1-f12, "
                f"ctrl, alt, shift, arrows, or single characters"
            )
    return out
