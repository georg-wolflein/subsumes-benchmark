r"""The validator the tests use reads patterns as ECMA-262 does with the ``u`` flag."""

from typing import TYPE_CHECKING

from subsumes_benchmark.validation import is_valid, pattern_error, search

if TYPE_CHECKING:
    from subsumes_benchmark import Json


def test_a_pattern_matches_anywhere_in_the_string() -> None:
    assert search("b", "abc")
    assert not search("^b", "abc")


def test_classes_are_those_of_ascii() -> None:
    assert not search(r"^\d$", "߀")  # NKO DIGIT ZERO
    assert not search(r"^\w$", "é")  # LATIN SMALL LETTER E WITH ACUTE
    assert search(r"^\s$", "\ufeff")  # ZERO WIDTH NO-BREAK SPACE, which has no White_Space property


def test_dot_matches_everything_but_a_line_terminator() -> None:
    for terminator in "\n\r\u2028\u2029":
        assert not search("^a.b$", f"a{terminator}b")
    assert search("^a.b$", "a\x0bb")


def test_a_character_is_a_code_point() -> None:
    assert search("^.$", "😀")
    assert search(r"^\u{1F600}$", "😀")
    assert search(r"^\p{Script=Greek}$", "α")


def test_dollar_matches_only_at_the_end() -> None:
    assert not search("^a$", "a\n")


def test_word_boundaries_look_around_and_backreferences_are_valid() -> None:
    assert search(r"\bfoo\b", "a foo b")
    assert search("^(?=a)a$", "a")
    assert search(r"^(a)\1$", "aa")
    assert search(r"^\cC$", "\x03")


def test_what_the_u_flag_forbids_is_not_valid() -> None:
    assert pattern_error(r"^4\-") is not None  # an escape of what needs none
    assert pattern_error("a{") is not None  # a brace that begins no quantifier
    assert pattern_error(r"[\w-/]") is not None  # a range that begins with a class
    assert pattern_error("(?i)a") is not None  # the flags of other dialects
    assert pattern_error(r"\p{greek}") is not None  # a property by another name than its own


def test_pattern_keywords_match_the_same_way() -> None:
    assert not is_valid("a\n", {"pattern": "^a$"})
    schema: Json = {
        "patternProperties": {r"^\d$": {"type": "integer"}},
        "additionalProperties": False,
    }
    assert is_valid({"1": 1}, schema)
    assert not is_valid({"1": "x"}, schema)
    assert not is_valid({"߀": 1}, schema)
    unevaluated: Json = {"patternProperties": {r"^\d$": True}, "unevaluatedProperties": False}
    assert is_valid({"1": 1}, unevaluated)
    assert not is_valid({"߀": 1}, unevaluated)
