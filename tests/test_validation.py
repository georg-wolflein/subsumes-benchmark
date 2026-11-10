r"""The validator the tests use reads patterns in the Rust regex dialect."""

from __future__ import annotations

from typing import TYPE_CHECKING

from validation import is_valid, pattern_error, search

if TYPE_CHECKING:
    from subsumes_benchmark import Json


def test_a_pattern_matches_anywhere_in_the_string() -> None:
    assert search("b", "abc")
    assert not search("^b", "abc")


def test_classes_are_unicode_aware() -> None:
    assert search(r"^\d$", "߀")  # NKO DIGIT ZERO
    assert search(r"^\w$", "é")  # LATIN SMALL LETTER E WITH ACUTE
    assert not search(r"^\s$", "﻿")  # ZERO WIDTH NO-BREAK SPACE has no White_Space property


def test_dot_matches_everything_but_a_line_feed() -> None:
    assert not search("^a.b$", "a\nb")
    assert search("^a.b$", "a\rb")


def test_dollar_matches_only_at_the_end() -> None:
    assert not search("^a$", "a\n")


def test_word_boundaries_are_part_of_the_dialect() -> None:
    assert pattern_error(r"\bfoo\b") is None
    assert search(r"\bfoo\b", "a foo b")


def test_look_around_and_backreferences_are_not() -> None:
    assert pattern_error("^(?=a)a$") is not None
    assert pattern_error(r"(a)\1") is not None
    assert pattern_error(r"^\cC$") is not None


def test_pattern_keywords_use_the_dialect() -> None:
    assert not is_valid("a\n", {"pattern": "^a$"})
    schema: Json = {
        "patternProperties": {r"^\d$": {"type": "integer"}},
        "additionalProperties": False,
    }
    assert is_valid({"߀": 1}, schema)
    assert not is_valid({"߀": "x"}, schema)
    unevaluated: Json = {"patternProperties": {r"^\d$": True}, "unevaluatedProperties": False}
    assert is_valid({"߀": 1}, unevaluated)
    assert not is_valid({"x": 1}, unevaluated)
