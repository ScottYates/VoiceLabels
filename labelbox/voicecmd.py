"""Spoken commands inside a recording.

    "space"        a space; also ends a spelled word ("T R A E space J O E" -> "Trae Joe")
    "start over"   clears all the text; words after it are kept
    "upper case"   EVERYTHING IN CAPITALS
    "lower case"   everything in small letters
    "title case"   Each Word Capitalized
    "remove ..."   takes something out of the whole text: "remove comma" drops
                   every ",", "remove dash" every "-", "remove punctuation" all
                   of it; anything else is removed as words ("remove Johnson")

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

# Spoken names of punctuation for "remove ...", one or two words.
PUNCT_NAMES = {
    "comma": ",", "period": ".", "dot": ".", "full stop": ".", "point": ".",
    "dash": "-\u2013\u2014", "hyphen": "-", "minus": "-",
    "colon": ":", "semicolon": ";", "semi colon": ";",
    "question mark": "?", "exclamation point": "!", "exclamation mark": "!",
    "exclamation": "!", "apostrophe": "'\u2019", "quote": "\"\u201c\u201d",
    "quotes": "\"\u201c\u201d", "quotation mark": "\"\u201c\u201d",
    "quotation marks": "\"\u201c\u201d", "slash": "/", "backslash": "\\",
    "back slash": "\\", "parenthesis": "()", "parentheses": "()", "brackets": "()[]",
    "bracket": "()[]", "ampersand": "&", "plus": "+", "plus sign": "+",
    "at sign": "@", "hash": "#", "pound sign": "#", "percent": "%",
    "percent sign": "%", "asterisk": "*", "star": "*", "underscore": "_",
}
ALL_PUNCT = ",.-\u2013\u2014:;?!'\u2019\"\u201c\u201d/\\()[]&+@#%*_"
_FILLER = {"and", "the", "all", "every", "any", "of", "a", "an", "s"}


def _punct_chars(words):
    """The characters named by words like ["comma", "and", "periods"], or None
    if any word isn't a punctuation name."""
    chars, i = "", 0
    while i < len(words):
        w = words[i]
        if w in _FILLER:
            i += 1
            continue
        if w in ("punctuation", "punctuations"):
            chars += ALL_PUNCT
            i += 1
            continue
        found = None
        for n in (2, 1):
            if i + n > len(words):
                continue
            phrase = " ".join(words[i:i + n])
            for cand in (phrase, phrase[:-1] if phrase.endswith("s") else None,
                         phrase[:-2] if phrase.endswith("es") else None):
                if cand in PUNCT_NAMES:
                    found = (PUNCT_NAMES[cand], n)
                    break
            if found:
                break
        if found:
            chars += found[0]
            i += found[1]
        else:
            if w and all(c in ALL_PUNCT for c in w):   # the recognizer wrote the symbol
                chars += w
                i += 1
                continue
            return None
    return chars or None


def _starts_command(toks, i):
    for n in range(_LONGEST, 0, -1):
        if tuple(_norm(t) for t in toks[i:i + n]) in PHRASES:
            return True
    return _norm(toks[i]) == "remove"


def _norm(tok: str) -> str:
    return tok.strip(_PUNCT).lower()


def _clean(tok: str) -> str:
    """Lowercase; keep a bare symbol ("-", ",") but strip punctuation off words."""
    low = tok.lower()
    core = low.strip(_PUNCT)
    return core if core else low


def apply_removals(text: str, removals) -> str:
    for kind, what in removals:
        if kind == "chars":
            text = "".join(c for c in text if c not in what)
        else:
            text = re.sub(r"(?<!\w)" + re.escape(what) + r"(?!\w)", "", text, flags=re.I)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return "\n".join(line.strip() for line in text.split("\n"))


def parse(spoken: str):
    """Return (text, case, cleared, commands_only, removals).

    text: what was said with the commands taken out, spoken "space" kept as
          SPACE markers (call finish() after other processing)
    case: "upper" / "lower" / "title" / None (the last one said wins)
    cleared: "start over" was said
    commands_only: nothing but commands was said
    removals: [("chars", ",.") or ("words", "Johnson"), ...] for apply_removals()
    """
    toks = spoken.split()
    out, case, cleared, removals, i = [], None, False, [], 0
    while i < len(toks):
        if _norm(toks[i]) == "remove" and i + 1 < len(toks):
            # "remove <what>": up to the next command or the end of the sentence
            j, target = i + 1, []
            while j < len(toks) and not (target and _starts_command(toks, j)):
                target.append(toks[j])
                j += 1
                if toks[j - 1][-1:] in ".!?" and len(toks[j - 1]) > 1:
                    break
            words = [w for w in (_clean(t) for t in target) if w]
            chars = _punct_chars(words)
            if chars:
                removals.append(("chars", chars))
            elif words:
                removals.append(("words", " ".join(t.strip(_PUNCT) for t in target)))
            if out and out[-1] != SPACE:
                out[-1] = out[-1].rstrip(".,") or out[-1]
            i = j
            continue
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
    return " ".join(out), case, cleared, not words_only, removals


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
