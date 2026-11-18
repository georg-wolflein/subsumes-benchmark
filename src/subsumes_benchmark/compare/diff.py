"""One run of a checker held against an earlier run of it, as a comment for a pull request.

This is for whoever develops a checker: the run of a change against the run of what the change
is based on. It says what a report on several checkers does not, task by task: which answers
are wrong, which tasks the base answered and the change no longer does, and which it answers
newly. Without a base it says how the run went and no more.
"""

import json
from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never

from subsumes_benchmark.compare.summary import outcome
from subsumes_benchmark.compare.words import count, duration, plural, table

if TYPE_CHECKING:
    from collections.abc import Sequence

    from subsumes_benchmark.compare.results import Result
    from subsumes_benchmark.compare.summary import Entry
    from subsumes_benchmark.compare.tasks import Direction

# At most this many entries in a list and rows in a table of tasks: GitHub caps a comment at
# 65,536 characters.
LIST_LIMIT = 40
TABLE_LIMIT = 10
# At most this many characters of a counterexample or of an error are shown.
SHOWN = 60

type Column = Literal["tasks", "yes", "no", "unknown", "wrong", "failed"]
"""What a task counts as in the table of a comment.

Every task is one of ``tasks`` and of one of ``yes``, ``no``, ``unknown`` and ``failed``. A
checker that was not asked, because its draft cannot express a schema, counts as ``unknown``,
and ``failed`` is an error, a crash or a timeout. ``wrong`` is counted besides: a yes or a no
that a label or a counterexample contradicts.
"""

COLUMNS: Sequence[Column] = ("tasks", "yes", "no", "unknown", "wrong", "failed")


@dataclass(frozen=True)
class Difference:
    """A run held against a base run.

    ``failures`` and ``lost`` are what a change should not be merged with: the first whatever
    the base says, the second unless the loss is accepted.
    """

    # The comment, as Markdown.
    comment: str
    # The wrong answers, and the tasks that ended in an error, a crash or a timeout.
    failures: int
    # The tasks that the base answered with yes or no and this run does not.
    lost: int


def _answered(result: Result) -> bool:
    return result.answer in ("yes", "no")


def _failed(result: Result) -> bool:
    return result.answer in ("error", "crash", "timeout")


def _wrong(result: Result) -> bool:
    return outcome(result) in ("wrong_no", "wrong_yes")


def _columns(result: Result) -> Sequence[Column]:
    match result.answer:
        case "yes" | "no":
            ended: Column = result.answer
        case "unknown" | "unsupported":
            ended = "unknown"
        case "error" | "crash" | "timeout":
            ended = "failed"
        case _:
            assert_never(result.answer)
    return ("tasks", ended, "wrong") if _wrong(result) else ("tasks", ended)


def _tally(results: Sequence[Result]) -> Counter[Column]:
    return Counter(column for result in results for column in _columns(result))


def _shortened(text: str) -> str:
    return text if len(text) <= SHOWN else text[:SHOWN] + "…"


def _name(result: Result) -> str:
    return f"`{result.case}` {result.direction}"


def _said(result: Result) -> str:
    """The answer, with the kind of reason of an unknown and the message of an error."""
    match result.answer:
        case "unknown" if result.reason is not None:
            return f"unknown ({result.reason})"
        case "error" | "crash" if result.detail:
            return f"{result.answer} ({_shortened(result.detail)})"
        case _:
            return result.answer


def _schemas(direction: Direction) -> tuple[str, str]:
    """The name in the case of the schema that was to accept, and of the one it was to accept."""
    match direction:
        case "a_subsumes_b":
            return "a", "b"
        case "b_subsumes_a":
            return "b", "a"
        case _:
            assert_never(direction)


def _described(result: Result) -> str:
    """The task with its answer, and with what is wrong with the answer if anything is."""
    faults = []
    contradicted = _answered(result) and result.expected == (result.answer != "yes")
    if contradicted:
        faults.append(f"the corpus says {'yes' if result.expected else 'no'}")
    if result.witness is not None and result.witness.refuted:
        accepting, accepted = _schemas(result.direction)
        instance = _shortened(json.dumps(result.witness.instance, ensure_ascii=False))
        match result.witness.confirmation:
            case "not_an_instance":
                faults.append(f"`{accepted}` rejects the counterexample `{instance}`")
            case "accepted":
                faults.append(f"`{accepting}` accepts the counterexample `{instance}`")
    described = f"{_name(result)}: {_said(result)}"
    return f"{described}, and {', and '.join(faults)}" if faults else described


def _change(now: int, before: int) -> str:
    """``+12`` or ``-12``."""
    return f"{'+' if now >= before else '-'}{count(abs(now - before))}"


def _with_change(now: int, before: int | None) -> str:
    """``1,234 (+12)``; the bare number without a base or when nothing changed."""
    if before is None or before == now:
        return count(now)
    return f"{count(now)} ({_change(now, before)})"


def _details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def _bullets(items: Sequence[str]) -> str:
    lines = [f"- {item}" for item in items[:LIST_LIMIT]]
    if len(items) > LIST_LIMIT:
        lines.append(f"- and {count(len(items) - LIST_LIMIT)} more")
    return "\n".join(lines)


def _transitions(pairs: Sequence[tuple[Result, Result]]) -> Sequence[str]:
    return [f"{_name(after)}: {_said(before)} to {_said(after)}" for before, after in pairs]


@dataclass(frozen=True)
class _Changes:
    """The tasks of both runs whose answer is of another kind now, as pairs of before and now."""

    # Not answered by the base and answered now.
    answered: Sequence[tuple[Result, Result]]
    # Answered by the base and not answered now.
    lost: Sequence[tuple[Result, Result]]
    # Answered by both, with yes by the one and no by the other.
    flipped: Sequence[tuple[Result, Result]]
    only_head: int
    only_base: int

    @classmethod
    def between(cls, head: Sequence[Result], base: Sequence[Result]) -> _Changes:
        before = {(result.case, result.direction): result for result in base}
        pairs = [
            (before[key], after)
            for after in head
            if (key := (after.case, after.direction)) in before
        ]
        return cls(
            answered=[(b, a) for b, a in pairs if not _answered(b) and _answered(a)],
            lost=[(b, a) for b, a in pairs if _answered(b) and not _answered(a)],
            flipped=[
                (b, a) for b, a in pairs if _answered(b) and _answered(a) and b.answer != a.answer
            ],
            only_head=len(head) - len(pairs),
            only_base=len(base) - len(pairs),
        )


def _tally_table(head: Sequence[Result], base: Sequence[Result] | None) -> str:
    """The answers per collection, each with its change against the base."""

    def per_collection(results: Sequence[Result]) -> dict[str, Counter[Column]]:
        found: dict[str, list[Result]] = {}
        for result in results:
            found.setdefault(result.collection, []).append(result)
        return {name: _tally(found[name]) for name in sorted(found)}

    def row(name: str, now: Counter[Column], before: Counter[Column] | None) -> Sequence[str]:
        cells = (_with_change(now[c], None if before is None else before[c]) for c in COLUMNS)
        return [name, *cells]

    before = None if base is None else per_collection(base)
    rows = [
        row(f"`{name}`", now, None if before is None else before.get(name, Counter()))
        for name, now in per_collection(head).items()
    ]
    rows.append(row("**total**", _tally(head), None if base is None else _tally(base)))
    return table(["collection", *COLUMNS], rows)


def _time(head: Entry, base: Entry | None, changes: _Changes | None) -> str:
    def spent(results: Sequence[Result]) -> str:
        return duration(sum(result.seconds or 0.0 for result in results))

    text = f"The checker took {spent(head.results)} for the tasks of this run"
    if base is not None:
        text += f", and {spent(base.results)} for those of the base"
    text += ". Times vary from one machine to the next."
    if base is not None and base.run.corpus != head.run.corpus:
        text += f" The base ran on corpus `{base.run.corpus}`."
    if changes is not None and changes.only_head + changes.only_base > 0:
        text += (
            f" The two runs are not over the same tasks: {count(changes.only_head)} only in "
            f"this run, {count(changes.only_base)} only in the base."
        )
    return text


def _counterexamples(head: Sequence[Result]) -> str | None:
    """What a validator made of the counterexamples.

    One that is none is a wrong answer and named among those; one that was not looked at is
    named here, with the reason.
    """
    witnesses = [(result, result.witness) for result in head if result.witness is not None]
    if not witnesses:
        return None
    confirmed = sum(1 for _, witness in witnesses if witness.confirmation == "confirmed")
    text = f"A validator confirms {count(confirmed)} of {plural(len(witnesses), 'counterexample')}."
    unchecked = [
        f"{_name(result)}: {witness.note}"
        for result, witness in witnesses
        if witness.confirmation == "unchecked"
    ]
    if unchecked:
        heading = f"{plural(len(unchecked), 'counterexample')} not checked"
        text += "\n\n" + _details(heading, _bullets(unchecked))
    return text


def _lost(pairs: Sequence[tuple[Result, Result]], allowed: bool, hint: str | None) -> str | None:
    if not pairs:
        return None
    if allowed:
        mark, consequence = ":warning:", "The loss is accepted."
    else:
        mark, consequence = ":x:", "The run fails for them." + (f" {hint}" if hint else "")
    heading = f"{plural(len(pairs), 'task')} no longer answered"
    return f"### {mark} {heading}\n\n{consequence}\n\n{_bullets(_transitions(pairs))}"


def _reasons(head: Sequence[Result], base: Sequence[Result] | None) -> str:
    """The kinds of reason for an unknown, counted."""

    def per_reason(results: Sequence[Result]) -> Counter[str]:
        return Counter(r.reason or "none given" for r in results if r.answer == "unknown")

    now = per_reason(head)
    before = None if base is None else per_reason(base)
    names = sorted({*now, *(before or ())}, key=lambda name: (-now[name], name))
    rows = [
        [f"`{name}`", _with_change(now[name], None if before is None else before[name])]
        for name in names
    ]
    body = table(["reason", "tasks"], rows) if rows else "None."
    return _details(f"Reasons for unknown ({plural(len(now), 'reason')})", body)


def _slowest(head: Sequence[Result]) -> str | None:
    timed = [(result.seconds, result) for result in head if result.seconds is not None]
    if not timed:
        return None
    timed.sort(key=lambda pair: -pair[0])
    rows = [[_name(r), _said(r), duration(seconds)] for seconds, r in timed[:TABLE_LIMIT]]
    return _details("The tasks that took the longest", table(["task", "answer", "time"], rows))


def diff(
    head: Entry,
    base: Entry | None = None,
    *,
    base_label: str | None = None,
    allow_lost: bool = False,
    lost_hint: str | None = None,
) -> Difference:
    """Hold a run against a base run of the same checker.

    Args:
        head: The run.
        base: The run to hold it against, if there is one.
        base_label: What the comment calls the base, such as its commit.
        allow_lost: Whether tasks that the base answered and this run does not are accepted.
        lost_hint: What the comment says about such tasks where they are not accepted, such as
            how to accept them.
    """
    # In the order of the cases, which is not the order in which a run asks them.
    results = sorted(head.results, key=lambda r: (r.case.split("/"), r.direction))
    changes = None if base is None else _Changes.between(results, base.results)
    wrong = [_described(result) for result in results if _wrong(result)]
    failed = [_described(result) for result in results if _failed(result)]
    run = head.run
    parts = [
        "## Benchmark",
        f"{run.name} {run.version} on corpus `{run.corpus}`, {plural(len(results), 'task')}. "
        + (
            "There is no run of the base to compare with."
            if base is None
            else f"Compared with {f'`{base_label}`' if base_label else 'the base'}."
        ),
        _tally_table(results, None if base is None else base.results),
        _time(head, base, changes),
        _counterexamples(results),
        f"### :x: {plural(len(wrong), 'wrong answer')}\n\n{_bullets(wrong)}" if wrong else None,
        f"### :x: {plural(len(failed), 'failed task')}\n\n{_bullets(failed)}" if failed else None,
        None if changes is None else _lost(changes.lost, allow_lost, lost_hint),
        _reasons(results, None if base is None else base.results),
    ]
    if changes is not None and changes.answered:
        heading = f":white_check_mark: {plural(len(changes.answered), 'task')} newly answered"
        parts.append(_details(heading, _bullets(_transitions(changes.answered))))
    if changes is not None and changes.flipped:
        heading = f":warning: {plural(len(changes.flipped), 'task')} changed between yes and no"
        parts.append(_details(heading, _bullets(_transitions(changes.flipped))))
    parts.append(_slowest(results))
    return Difference(
        comment="\n\n".join(part for part in parts if part is not None) + "\n",
        failures=len(wrong) + len(failed),
        lost=0 if changes is None else len(changes.lost),
    )
