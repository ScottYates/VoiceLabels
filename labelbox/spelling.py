"""Spot spelled-out words in recognized speech and join the letters.

With joiner "" (the default in config.py) and case "name":
    "my name is S M I T H"          -> "my name is Smith"
    "J-A-N-E. Doe."             -> "Jane Doe."
    "part A, B, C, 1, 2, 3."        -> "part ABC123"
    "S M eye T H"                   -> "Smith"
    "Plan B" / "vitamin C" / "I a"  -> unchanged
With joiner "-": "S-M-I-T-H", "A-B-C-1-2-3".

A run counts as spelling when it has at least two single letters or digits
in a row (with at least one letter, and not just "a"/"I" on their own), or
three or more tokens where letter names like "bee" and "ess" fill in
between single letters. Letter names only count inside such a run, so
ordinary words like "see", "you" and "why" are left alone elsewhere.
"""

from __future__ import annotations

import re

# Spoken names of letters, as speech recognition tends to write them.
LETTER_NAMES = {
    "ay": "A", "aye": "A", "bee": "B", "be": "B", "cee": "C", "see": "C", "sea": "C",
    "dee": "D", "ee": "E", "ef": "F", "eff": "F", "gee": "G", "jee": "G",
    "aitch": "H", "haitch": "H", "eye": "I", "jay": "J", "kay": "K", "kaye": "K",
    "el": "L", "ell": "L", "em": "M", "en": "N", "oh": "O", "pee": "P", "pea": "P",
    "cue": "Q", "queue": "Q", "ar": "R", "are": "R", "es": "S", "ess": "S",
    "tee": "T", "tea": "T", "you": "U", "vee": "V", "ex": "X", "why": "Y", "wye": "Y",
    "zee": "Z", "zed": "Z",
}
DIGIT_NAMES = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
               "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9"}

_PUNCT = ",.;:!?\"'()"
_DOTTED = re.compile(r"^(?:[A-Za-z0-9]\.){2,}[A-Za-z0-9]?\.?$")     # S.M.I.T.H. / A.B.C
_HYPHENED = re.compile(r"^[A-Za-z0-9](?:-[A-Za-z0-9])+$")           # S-M-I-T-H


def _classify(tok: str):
    """Return (kind, letters) for one word: kind is 'strong' (a single letter
    or digit, or an already dotted/hyphenated spelling), 'name' (a letter or
    digit name), or None."""
    core = tok.strip(_PUNCT) if not _DOTTED.match(tok) else tok
    if not core:
        return None, ""
    if _DOTTED.match(core):
        return "strong", [c.upper() for c in core if c.isalnum()]
    if _HYPHENED.match(core):
        return "strong", [c.upper() for c in core.split("-")]
    if core == "a":
        return "name", ["A"]                          # the word "a": a letter only inside a run
    if len(core) == 1 and core.isalnum():
        return "strong", [core.upper()]
    if core.isdigit() and len(core) <= 4:
        return "num", [core]                          # "R J 45" -> R-J-45, only inside a run
    low = core.lower()
    if low in LETTER_NAMES:
        return "name", [LETTER_NAMES[low]]
    if low in DIGIT_NAMES:
        return "name", [DIGIT_NAMES[low]]
    return None, ""


def _is_spelling(run) -> bool:
    letters = [c for _, _, cs in run for c in cs]
    strong = [cs for _, kind, cs in run if kind == "strong"]
    run = [r for r in run if r[1] != "num"]           # numbers ride along but don't decide
    strong_chars = [c for cs in strong for c in cs]
    if not any(c.isalpha() for c in letters):
        return False                                  # digits only: leave numbers alone
    if any(len(cs) > 1 for cs in strong):
        return True                                   # S.M.I.T.H. or S-M-I-T-H already
    if len(strong) >= 2 and len(strong) * 2 >= len(run):
        return set(strong_chars) - {"A", "I"} != set() or len(strong) >= 3
    if len(run) >= 3 and len(strong) >= 1 and len(strong) * 3 >= len(run):
        return True                                   # "S em eye tee H"
    return False


def _case(chars, joiner, case):
    word = joiner.join(chars)
    if case == "upper" or (case == "name" and any(c.isdigit() for c in chars)):
        return word.upper()
    if case == "lower":
        return word.lower()
    return word[:1].upper() + word[1:].lower()       # "name": Jane


def _multi(tok):
    """A token that is already a whole spelled word: S-M-I-T-H or S.M.I.T.H."""
    k, cs = _classify(tok)
    return k == "strong" and len(cs) > 1


def hyphenate_spelling(text: str, joiner: str = "-", case: str = "upper") -> str:
    words = text.split(" ")
    out, i = [], 0
    while i < len(words):
        kind, chars = _classify(words[i])
        if kind is None:
            out.append(words[i])
            i += 1
            continue
        # gather the longest run of letter-ish words starting here; a word
        # ending in . ! or ? (other than a dotted spelling) ends the run
        j, run = i, []
        while j < len(words):
            if words[j] in ("-", "–", "—") and run and j + 1 < len(words) \
                    and _classify(words[j + 1])[0] is not None:
                j += 1                                # "S - M - I": spoken dashes between letters
                continue
            k, cs = _classify(words[j])
            if k is None:
                break
            if run and (_multi(words[j]) or _multi(run[-1][0])):
                break                                 # "J-O-H-N S-M-I-T-H": two words
            run.append((words[j], k, cs))
            j += 1
            prev = words[j - 1]
            # "word." ends a sentence and the run; "S." (one letter) is just a spelled letter
            if prev[-1:] in ".!?" and len(prev.strip(_PUNCT)) > 1 and not _DOTTED.match(prev) \
                    and len(run) >= 2:
                break
        # a run has to start and end on a real letter or digit, not a letter name
        start, popped = i, 0
        while run and run[0][1] != "strong":
            out.append(run.pop(0)[0])
            popped += 1
        if not run:
            i = start + popped                        # nothing left: carry on after what we passed
            continue
        trail = []
        while run and run[-1][1] == "name":
            trail.insert(0, run.pop()[0])
        initials = len(run) <= 3 and all(re.fullmatch(r"[A-Za-z]\.", w) for w, _, _ in run)
        if run and _is_spelling(run) and not initials:   # "J. R. R. Tolkien" stays as it is
            last = run[-1][0]
            end = "" if _DOTTED.match(last) else last[len(last.rstrip(_PUNCT)):]
            if end == ".":
                end = ""                              # "H." / "J-A-N-E." - the recognizer's period
            out.append(_case([c for _, _, cs in run for c in cs], joiner, case) + end)
        else:
            out.extend(w for w, _, _ in run)
        out.extend(trail)
        i = j
    return " ".join(out)
