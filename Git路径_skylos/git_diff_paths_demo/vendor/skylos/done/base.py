"""Verbatim extraction from skylos' skylos/done/base.py.

Revision: 380b2a3e315ca05f5546139c691b678114e38dc4
License: Apache-2.0 (see ../LICENSE)
"""

def _unquote_c_style(value: str) -> str:
    """Undo Git's C-style path quoting (``\\t``, ``\\"``, octal bytes)."""
    out = bytearray()
    index = 0
    escapes = {
        "n": 10,
        "t": 9,
        '"': 34,
        "\\": 92,
        "a": 7,
        "b": 8,
        "f": 12,
        "r": 13,
        "v": 11,
    }
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            nxt = value[index + 1]
            if nxt in escapes:
                out.append(escapes[nxt])
                index += 2
                continue
            octal = value[index + 1 : index + 4]
            if len(octal) == 3 and all(c in "01234567" for c in octal):
                out.append(int(octal, 8))
                index += 4
                continue
        out.extend(char.encode("utf-8"))
        index += 1
    return out.decode("utf-8", errors="replace")
