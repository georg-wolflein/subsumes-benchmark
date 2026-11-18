"""A run held against a base run: what the comment says and what fails."""

import subprocess
import sys
from typing import TYPE_CHECKING

import runs
from runs import Confirmation, a_run, a_witness
from subsumes_benchmark.compare.diff import LIST_LIMIT, diff
from subsumes_benchmark.compare.results import Ending, Result, result_line, write_run
from subsumes_benchmark.compare.summary import Entry

if TYPE_CHECKING:
    from pathlib import Path


def a_result(
    case: str,
    ended: Ending,
    expected: bool | None = None,
    *,
    seconds: float = 0.001,
    reason: str | None = None,
    message: str | None = None,
    witness: Confirmation | None = None,
) -> Result:
    """A result whose witness, where it has one, holds the counterexample ``{"x": 1}``."""
    given = None if witness is None else a_witness(witness, {"x": 1}, message or "why")
    said = None if ended == "no" else message
    return runs.a_result(
        case, ended, expected, seconds=seconds, reason=reason, message=said, witness=given
    )


def an_entry(*results: Result, corpus: str = "v1.0.0") -> Entry:
    return Entry(a_run(corpus=corpus), results)


def test_without_a_base_the_comment_only_tallies() -> None:
    found = diff(
        an_entry(
            a_result("one/a", "yes", True, seconds=2.0),
            a_result("one/b", "unknown", reason="budget"),
            a_result("two/a", "no", False, witness="confirmed"),
        )
    )
    assert (found.failures, found.lost) == (0, 0)
    comment = found.comment
    assert "One 1.0 on corpus `v1.0.0`, 3 tasks. There is no run of the base" in comment
    assert "| `one` | 2 | 1 | 0 | 1 | 0 | 0 |" in comment
    assert "| `two` | 1 | 0 | 1 | 0 | 0 | 0 |" in comment
    assert "| **total** | 3 | 1 | 1 | 1 | 0 | 0 |" in comment
    assert "The checker took 2.0 s for the tasks of this run." in comment
    assert "| `budget` | 1 |" in comment
    assert "A validator confirms 1 of 1 counterexample." in comment
    assert "| `one/a` a_subsumes_b | yes | 2.0 s |" in comment
    assert ":x:" not in comment


def test_a_run_without_a_counterexample_says_nothing_of_them() -> None:
    found = diff(an_entry(a_result("one/a", "yes"), a_result("one/b", "no", False)))
    assert "counterexample" not in found.comment


def test_a_counterexample_that_is_none_is_a_wrong_answer() -> None:
    found = diff(
        an_entry(
            a_result("one/a", "no", False, witness="confirmed"),
            a_result("one/b", "no", False, witness="not_an_instance"),
            a_result("one/c", "no", witness="accepted"),
        )
    )
    assert found.failures == 2
    comment = found.comment
    assert "A validator confirms 1 of 3 counterexamples." in comment
    assert "### :x: 2 wrong answers" in comment
    assert '- `one/b` a_subsumes_b: no, and `b` rejects the counterexample `{"x": 1}`' in comment
    assert '- `one/c` a_subsumes_b: no, and `a` accepts the counterexample `{"x": 1}`' in comment
    assert "| **total** | 3 | 0 | 3 | 0 | 2 | 0 |" in comment


def test_a_counterexample_that_was_not_checked_is_named_with_the_reason() -> None:
    found = diff(
        an_entry(
            a_result("one/a", "no", False, witness="confirmed"),
            a_result("one/b", "no", witness="unchecked", message="the validator does not take it"),
        )
    )
    assert found.failures == 0
    comment = found.comment
    assert "A validator confirms 1 of 2 counterexamples." in comment
    assert "<summary>1 counterexample not checked</summary>" in comment
    assert "- `one/b` a_subsumes_b: the validator does not take it" in comment
    assert ":x:" not in comment


def test_a_task_that_the_base_answered_is_lost_when_it_is_not_answered_now() -> None:
    base = an_entry(a_result("one/a", "yes"), a_result("one/b", "no"))
    head = an_entry(a_result("one/a", "unknown", reason="budget"), a_result("one/b", "no"))

    refused = diff(head, base, lost_hint="Add the label `allow` to accept them.")
    assert (refused.failures, refused.lost) == (0, 1)
    assert "### :x: 1 task no longer answered" in refused.comment
    assert "The run fails for them. Add the label `allow` to accept them." in refused.comment
    assert "- `one/a` a_subsumes_b: yes to unknown (budget)" in refused.comment
    assert "| **total** | 2 | 0 (-1) | 1 | 1 (+1) | 0 | 0 |" in refused.comment
    assert "| `budget` | 1 (+1) |" in refused.comment

    accepted = diff(head, base, allow_lost=True, lost_hint="Add the label.")
    assert accepted.lost == 1
    assert "### :warning: 1 task no longer answered" in accepted.comment
    assert "The loss is accepted." in accepted.comment
    assert "Add the label." not in accepted.comment


def test_newly_answered_and_flipped_tasks_are_listed_and_lose_nothing() -> None:
    base = an_entry(a_result("one/a", "unknown", reason="format"), a_result("one/b", "yes"))
    head = an_entry(a_result("one/a", "yes"), a_result("one/b", "no"))
    found = diff(head, base, base_label="abc1234")
    assert (found.failures, found.lost) == (0, 0)
    comment = found.comment
    assert "Compared with `abc1234`." in comment
    assert ":white_check_mark: 1 task newly answered" in comment
    assert "- `one/a` a_subsumes_b: unknown (format) to yes" in comment
    assert ":warning: 1 task changed between yes and no" in comment
    assert "- `one/b` a_subsumes_b: yes to no" in comment
    # A reason that only the base has is still a row.
    assert "| `format` | 0 (-1) |" in comment


def test_a_wrong_answer_and_a_failed_task_are_named() -> None:
    found = diff(
        an_entry(
            a_result("one/a", "no", True),
            a_result("one/b", "yes", False),
            a_result("one/c", "error", message="no schema"),
            a_result("one/d", "timeout"),
        )
    )
    assert found.failures == 4
    comment = found.comment
    assert "### :x: 2 wrong answers" in comment
    assert "- `one/a` a_subsumes_b: no, and the corpus says yes" in comment
    assert "- `one/b` a_subsumes_b: yes, and the corpus says no" in comment
    assert "### :x: 2 failed tasks" in comment
    assert "- `one/c` a_subsumes_b: error (no schema)" in comment
    assert "- `one/d` a_subsumes_b: timeout" in comment
    assert "| **total** | 4 | 1 | 1 | 0 | 2 | 2 |" in comment


def test_tasks_in_only_one_run_are_counted_and_not_compared() -> None:
    base = an_entry(a_result("one/a", "yes"), a_result("one/old", "yes"), corpus="v0.9.0")
    head = an_entry(a_result("one/a", "yes"), a_result("one/new", "unknown"))
    found = diff(head, base)
    assert found.lost == 0
    assert "The base ran on corpus `v0.9.0`." in found.comment
    assert "not over the same tasks: 1 only in this run, 1 only in the base." in found.comment


def test_the_tasks_are_named_in_the_order_of_the_cases_and_long_lists_are_cut() -> None:
    wrong = [a_result(f"one/{n:03}", "no", True) for n in reversed(range(LIST_LIMIT + 2))]
    comment = diff(an_entry(*wrong)).comment
    listed = [line for line in comment.splitlines() if line.startswith("- ")]
    assert listed[0].startswith("- `one/000` ")
    assert listed[-2].startswith(f"- `one/{LIST_LIMIT - 1:03}` ")
    assert listed[-1] == "- and 2 more"


def test_the_command_writes_the_comment_and_fails_for_what_should_not_be_merged(
    tmp_path: Path,
) -> None:
    def write(name: str, *results: Result) -> Path:
        folder = tmp_path / name
        folder.mkdir()
        write_run(folder, a_run())
        lines = "".join(map(result_line, results))
        (folder / "results.jsonl").write_text(lines, encoding="utf-8")
        return folder

    def command(*arguments: str | Path) -> int:
        words = [sys.executable, "-m", "subsumes_benchmark.compare", "diff", *map(str, arguments)]
        return subprocess.run(words, check=False, capture_output=True).returncode

    base = write("base", a_result("one/a", "yes"))
    lost = write("lost", a_result("one/a", "unknown"))
    wrong = write("wrong", a_result("one/a", "no", True))
    out = tmp_path / "comment.md"
    assert command(base, "--base", base, "--out", out) == 0
    assert out.read_text(encoding="utf-8").startswith("## Benchmark\n")
    assert command(lost, "--base", base) == 1
    assert command(lost, "--base", base, "--allow-lost") == 0
    assert command(lost) == 0
    assert command(wrong, "--base", base, "--allow-lost") == 1
