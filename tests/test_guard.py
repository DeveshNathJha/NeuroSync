"""Tests for the interpretive-language guard."""

from src.reporting import guard


def test_check_finds_terms_case_insensitive():
    text = "The child shows Autistic traits. Possible DIAGNOSIS: ASD. A meltdown occurred."
    found = [t.lower() for t in guard.check(text)]
    for term in ("autistic", "diagnosis", "asd", "meltdown"):
        assert term in found


def test_check_clean_text():
    assert guard.check("Repetitive hand/arm movement at 01:10 for 4 seconds.") == []


def test_sanitize_replaces_only_offending_sentences():
    text = "Hand movement at 00:10. This indicates a developmental delay. Loud sound at 00:40."
    out = guard.sanitize(text)
    assert "developmental" not in out
    assert "Hand movement at 00:10." in out and "Loud sound at 00:40." in out
    assert guard.REPLACEMENT in out
    assert guard.check(out) == []


def test_sanitize_keeps_line_structure():
    text = "Line one.\nThe patient has a disorder.\nLine three."
    out = guard.sanitize(text).split("\n")
    assert out[0] == "Line one." and out[2] == "Line three." and guard.REPLACEMENT in out[1]
