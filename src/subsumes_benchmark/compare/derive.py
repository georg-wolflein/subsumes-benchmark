"""Labels for the questions that upstream leaves open, from the answers of checkers.

A run with ``--unlabelled`` asks a checker the questions that have no label. This reads such
runs and writes ``derived.json``, from which the build gives the cases their labels:

- The answer is **no** where a checker gave a counterexample and the instance is valid under
  the schema whose instances must be accepted and not under the other, to both validators
  of ``subsumes_benchmark.validation``. That is a proof, whichever checker found the instance
  and however often that checker is wrong.
- The answer is **yes** where at least two checkers say so, none says no, and the schemas use
  neither a pattern nor a format, nor a number that a double does not hold. Checkers read
  those in their own ways, so what they say about schemas that use them is not about the
  question the corpus asks. This is evidence and no proof.
- Everything else stays open, and so does every question of a case that ``overrides.json``
  lists: an override states both labels of its cases, also where it claims nothing.

A question that hinges on digits that a double does not hold is not in the corpus. So a
counterexample holds only such numbers as a double holds, and it must refute the schemas
also as someone reads them who reads every number as a double.

What ``derived.json`` holds already is evidence like the answers of a run: a counterexample
is held against the schemas again, and the checkers of an agreement count as having said
yes. So a later run adds to the file, and a counterexample replaces an agreement that it
refutes.
"""

import json
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, assert_never

from subsumes_benchmark import Json
from subsumes_benchmark.cases import read_case
from subsumes_benchmark.compare.results import read_results, read_run
from subsumes_benchmark.compare.tasks import case_files, collection_of, read_unlabelled
from subsumes_benchmark.derived import Derivations, by_label
from subsumes_benchmark.generated.case import Feature, GeneratedCase, Schema, UpstreamCase
from subsumes_benchmark.generated.derived import Agreement, Counterexample, Derived, Evidence
from subsumes_benchmark.generated.result import (
    Crash,
    Direction,
    Error,
    No,
    Timeout,
    Unknown,
    Unsupported,
    Yes,
)
from subsumes_benchmark.validation import is_valid, is_valid_to_another, meaningless

type Question = tuple[str, Direction]
"""A case and the direction asked."""

type Open = Literal[
    "no meaning", "overridden", "contradicted", "read differently", "one yes", "no answer"
]
"""Why a question stays open.

- ``no meaning``: the corpus cannot say what one of the schemas accepts.
- ``overridden``: an override states the labels of the case, also where it claims nothing.
- ``contradicted``: a checker says no and gave no instance that proves it.
- ``read differently``: checkers say yes about schemas that they read in their own ways.
- ``one yes``: one checker says yes and no other does.
- ``no answer``: no checker says yes or no.
"""

type Outcome = Literal["true", "false"] | Open
"""What became of a question: the label it got, or why it stays open."""

OUTCOMES: Sequence[Outcome] = (
    "true",
    "false",
    "no meaning",
    "overridden",
    "contradicted",
    "read differently",
    "one yes",
    "no answer",
)

# What checkers read in their own ways, so that their yes is about another question. So do
# they read a number that a double does not hold, which is no feature.
READ_DIFFERENTLY: frozenset[Feature] = frozenset({"format", "pattern", "patternProperties"})

# The name under which a counterexample that ``derived.json`` holds already is held against
# the schemas again.
ON_FILE = "derived.json"


@dataclass(frozen=True)
class Vote:
    """What one checker says about one question.

    ``checker`` is the checker with its version, as an agreement names it, and ``name`` the
    checker alone: two variants or two versions of one checker are one voice.
    """

    checker: str
    name: str
    answer: Literal["yes", "no"]
    counterexample: str | None = None
    """The instance that the checker gave with a no, as JSON text."""

    @classmethod
    def of_agreement(cls, agreement: Agreement) -> Sequence[Vote]:
        return [cls(checker, checker.rpartition(" ")[0], "yes") for checker in agreement.checkers]


def read_votes(folders: Sequence[Path]) -> Mapping[Question, Sequence[Vote]]:
    """The yes and no answers of the runs in the folders, by question."""
    votes: dict[Question, list[Vote]] = {}
    for folder in folders:
        checker = read_run(folder).checker
        named = f"{checker.label} {checker.version}"
        for result in read_results(folder):
            match result:
                case Yes():
                    vote = Vote(named, checker.label, "yes")
                case No():
                    vote = Vote(named, checker.label, "no", _counterexample(result))
                case Unknown() | Error() | Timeout() | Unsupported() | Crash():
                    continue
                case _:
                    assert_never(result)
            votes.setdefault((result.case, result.direction), []).append(vote)
    return votes


def _counterexample(no: No) -> str | None:
    """The instance that a checker gave with its no, whatever the validator of the run made of it.

    The key and not its value says whether there is one: ``null`` is an instance.
    """
    witness = no.witness
    if witness is None or "counterexample" not in witness.model_fields_set:
        return None
    return json.dumps(witness.counterexample)


def _is_double(number: int) -> bool:
    try:
        return int(float(number)) == number
    except OverflowError:
        return False


def exact(value: Json) -> bool:
    """Whether a double holds every number of the value, a schema or an instance."""
    pending = [value]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
        elif isinstance(node, int) and not isinstance(node, bool) and not _is_double(node):
            return False
    return True


def _doubles(value: Json) -> Json:
    if isinstance(value, dict):
        return {key: _doubles(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_doubles(item) for item in value]
    if isinstance(value, int) and not isinstance(value, bool) and not _is_double(value):
        return float(value)
    return value


def as_doubles(schema: Schema) -> Schema:
    """The schema as someone reads it who reads every number as a double.

    Raises:
        OverflowError: A number is beyond every double.
    """
    if isinstance(schema, bool):
        return schema
    return {key: _doubles(item) for key, item in schema.items()}


def _instances(votes: Sequence[Vote]) -> Iterator[Json]:
    """The instances that the votes give as counterexamples, the shortest first."""
    texts = {vote.counterexample for vote in votes if vote.counterexample is not None}
    for text in sorted(texts, key=lambda text: (len(text), text)):
        try:
            # A number that JSON does not have, such as NaN, is no instance.
            instance = json.loads(text, parse_constant=_no_instance)
        except ValueError:
            continue
        if exact(instance):
            yield instance


def _no_instance(constant: str) -> Json:
    raise ValueError(constant)


def refutes(instance: Json, accepting: Schema, narrower: Schema) -> bool:
    """Whether the instance proves that ``accepting`` does not accept all of ``narrower``.

    Two validators that share no code must both say so, of the schemas as they are written
    and as someone reads them who reads every number as a double. A validator that fails on
    the schemas proves nothing.
    """
    try:
        readings = [(accepting, narrower)]
        if not (exact(accepting) and exact(narrower)):
            readings.append((as_doubles(accepting), as_doubles(narrower)))
        return all(
            valid(instance, narrow) and not valid(instance, wide)
            for valid in (is_valid, is_valid_to_another)
            for wide, narrow in readings
        )
    except Exception:
        return False


def decide(
    case: UpstreamCase | GeneratedCase, direction: Direction, votes: Sequence[Vote]
) -> Evidence | Open:
    """What the votes show about one question of a case, or why it stays open."""
    match direction:
        case "a_subsumes_b":
            accepting, narrower = case.a, case.b
        case "b_subsumes_a":
            accepting, narrower = case.b, case.a
        case _:
            assert_never(direction)
    if meaningless(case.a) is not None or meaningless(case.b) is not None:
        return "no meaning"
    if isinstance(case, UpstreamCase) and case.note is not None:
        return "overridden"
    for instance in _instances(votes):
        if refutes(instance, accepting, narrower):
            return Counterexample(counterexample=instance)
    if any(vote.answer == "no" for vote in votes):
        return "contradicted"
    agreeing = sorted({vote.checker for vote in votes})
    if not agreeing:
        return "no answer"
    if len({vote.name for vote in votes}) < 2:
        return "one yes"
    if READ_DIFFERENTLY & set(case.features) or not (exact(case.a) and exact(case.b)):
        return "read differently"
    return Agreement(checkers=agreeing)


def derive(corpus: Path, derived_file: Path, runs: Sequence[Path]) -> None:
    """Add what the runs show to ``derived.json`` and print what became of every question."""
    before = Derivations.read(derived_file).cases if derived_file.exists() else {}
    votes = {question: list(found) for question, found in read_votes(runs).items()}
    asked = {(task.case, task.direction) for task in read_unlabelled(corpus)}
    for case, entry in before.items():
        for direction, evidence in by_label(entry):
            asked.add((case, direction))
            match evidence:
                case Counterexample():
                    text = json.dumps(evidence.counterexample)
                    votes.setdefault((case, direction), []).append(
                        Vote(ON_FILE, ON_FILE, "no", text)
                    )
                case Agreement():
                    votes.setdefault((case, direction), []).extend(Vote.of_agreement(evidence))
                case _:
                    assert_never(evidence)

    files = case_files(corpus)
    after: dict[str, dict[Direction, Evidence]] = {}
    outcomes: Counter[tuple[str, Outcome]] = Counter()
    refuted: list[str] = []
    for case, direction in sorted(asked, key=lambda question: question[0].split("/")):
        found = votes.get((case, direction), [])
        decided = decide(read_case(files[case]), direction, found)
        collection = collection_of(case)
        match decided:
            case Counterexample():
                outcomes[collection, "false"] += 1
                if wrong := sorted({vote.checker for vote in found if vote.answer == "yes"}):
                    refuted.append(f"{case} {direction}: {', '.join(wrong)}")
            case Agreement():
                outcomes[collection, "true"] += 1
            case _:
                outcomes[collection, decided] += 1
                continue
        after.setdefault(case, {})[direction] = decided
    Derivations.write(derived_file, {case: Derived(**entry) for case, entry in after.items()})

    print(f"{'collection':40s}" + "".join(f"{outcome:>19s}" for outcome in OUTCOMES))
    for collection in sorted({collection for collection, _ in outcomes}):
        counts = (outcomes[collection, outcome] for outcome in OUTCOMES)
        print(f"{collection:40s}" + "".join(f"{count:19d}" for count in counts))
    totals = (sum(n for (_, o), n in outcomes.items() if o == outcome) for outcome in OUTCOMES)
    print(f"{'all':40s}" + "".join(f"{total:19d}" for total in totals))
    if refuted:
        print(f"\na checker says yes where a counterexample proves no, on {len(refuted)}:")
        for line in refuted:
            print(f"  {line}")
