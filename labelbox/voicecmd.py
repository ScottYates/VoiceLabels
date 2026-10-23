"""Spoken commands inside a recording.

    "space"        a space; also ends a spelled word ("T R A E space J O E" -> "Trae Joe")
    "start over"   clears all the text; words after it are kept
    "upper case"   EVERYTHING IN CAPITALS
    "lower case"   everything in small letters
    "title case"   Each Word Capitalized

parse() pulls the commands out of what was heard. The case commands apply to
the whole label, including text already in the box, so saying just "upper case"
changes the existing text without replacing it.
"""

from __future__ import annotations

import re

SPACE = "\x00"                       # stands for a spoken "space" until the end
_PUNCT = ",.;:!?\"'()"

PHRASES = {                          # spoken (lowercase, no punctuation) -> command
    ("start", "over"): "clear",
    ("upper", "case"): "upper",
    ("lower", "case"): "lower",
    ("title", "case"): "title",
    ("uppercase",): "upper",
    ("lowercase",): "lower",
    ("titlecase",): "title",
    ("upper-case",): "upper",
    ("lower-case",): "lower",
    ("title-case",): "title",
    ("all", "caps"): "upper",
    ("space",): "space",
}
_LONGEST = max(len(k) for k in PHRASES)


def _norm(tok: str) -> str:
    return tok.strip(_PUNCT).lower()


def parse(spoken: str):
    """Return (text, case, cleared, commands_only).

    text: what was said with the commands taken out, spoken "space" kept as
          SPACE markers (call finish() after other processing)
    case: "upper" / "lower" / "title" / None (the last one said wins)
    cleared: "start over" was said
    commands_only: nothing but commands was said
    """
    toks = spoken.split()
    out, case, cleared, i = [], None, False, 0
    while i < len(toks):
        for n in range(_LONGEST, 0, -1):
            key = tuple(_norm(t) for t in toks[i:i + n])
            if len(key) == n and key in PHRASES:
                cmd = PHRASES[key]
                if cmd == "clear":
                    out, cleared = [], True
                elif cmd == "space":
                    if out:                      # the period the recognizer put before
                        out[-1] = out[-1].rstrip(".") or out[-1]
                    out.append(SPACE)
                else:
                    case = cmd
                    if out and out[-1] != SPACE:
                        out[-1] = out[-1].rstrip(".,") or out[-1]
                i += n
                break
        else:
            out.append(toks[i])
            i += 1
    words_only = [t for t in out if t != SPACE]
    return " ".join(out), case, cleared, not words_only


def finish(text: str) -> str:
    """Turn SPACE markers into exactly one space each."""
    text = re.sub(f" ?{SPACE} ?", SPACE, text)
    return text.replace(SPACE, " ")


def apply_case(text: str, case: str | None) -> str:
    if case == "upper":
        return text.upper()
    if case == "lower":
        return text.lower()
    if case == "title":
        return re.sub(r"[^\s]+", lambda m: _title_word(m.group(0)), text)
    return text


def _title_word(w: str) -> str:
    for i, c in enumerate(w):
        if c.isalpha():
            return w[:i] + c.upper() + w[i + 1:].lower()
    return w
