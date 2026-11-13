"""
src/reporting/guard.py
----------------------
Keeps generated text descriptive. NeuroSync records what was observed; it
must not state or suggest a diagnosis, condition or clinical interpretation.

check()    -> the offending terms found in a text
sanitize() -> the text with every sentence containing such a term replaced

Applied to every report, whether written by the template or by an LLM.
"""

from __future__ import annotations

import re

REPLACEMENT = "[removed: interpretive statement]"

# Case-insensitive patterns for interpretive / diagnostic language
DIAGNOSTIC_TERMS: list[str] = [
    r"\bdiagnos\w*",
    r"\bautis\w*",
    r"\bASD\b",
    r"\bdisorders?\b",
    r"\bDSM\b",
    r"\bsymptoms?\b",
    r"\bsymptomatic\b",
    r"\bmeltdowns?\b",
    r"\bscreening\b",
    r"\bclinical(ly)? significant\b",
    r"\bindicat\w* (of|that) (a |an )?(condition|disorder|disability|delay)\b",
    r"\b(suffers?|suffering) from\b",
    r"\bpatient (is|has)\b",
    r"\bdevelopmental (delay|disability)\b",
    r"\bneurodevelopmental\b",
    r"\bADHD\b",
    r"\bpatholog\w*",
    r"\babnormal\w*",
    r"\bprognos\w*",
    r"\btreatment plan\b",
]
_PATTERNS = [re.compile(p, re.IGNORECASE) for p in DIAGNOSTIC_TERMS]
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?|\n")


def check(text: str) -> list[str]:
    """Return the distinct offending terms found in text (as they appear)."""
    found: list[str] = []
    for pattern in _PATTERNS:
        for m in pattern.finditer(text or ""):
            term = m.group(0)
            if term.lower() not in (f.lower() for f in found):
                found.append(term)
    return found


def sanitize(text: str) -> str:
    """Replace each sentence that contains an offending term."""
    out = []
    for part in _SENTENCE.findall(text or ""):
        if part != "\n" and any(p.search(part) for p in _PATTERNS):
            lead = part[: len(part) - len(part.lstrip())]
            out.append(f"{lead}{REPLACEMENT}")
        else:
            out.append(part)
    return "".join(out)
