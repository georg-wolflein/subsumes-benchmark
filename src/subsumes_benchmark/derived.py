"""``derived.json``: the labels that the corpus has where upstream has none.

``python -m subsumes_benchmark.compare derive`` writes the file from the answers of checkers,
and the build reads it. An entry holds what shows the label, and the label follows from it:
a counterexample shows false, and an agreement of checkers true.
"""

import json
from collections import Counter
from typing import TYPE_CHECKING, Self, assert_never

from pydantic import model_validator

from subsumes_benchmark.generated.derived import (
    Agreement,
    Counterexample,
    Derived,
    DerivedSpec,
    Evidence,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

    from subsumes_benchmark import Json
    from subsumes_benchmark.compare.tasks import Direction


def label(evidence: Evidence) -> bool:
    """The label that the evidence shows."""
    match evidence:
        case Counterexample():
            return False
        case Agreement():
            return True
        case _:
            assert_never(evidence)


def by_label(entry: Derived) -> Iterator[tuple[Direction, Evidence]]:
    """What an entry holds, by the label it is about."""
    if entry.a_subsumes_b is not None:
        yield "a_subsumes_b", entry.a_subsumes_b
    if entry.b_subsumes_a is not None:
        yield "b_subsumes_a", entry.b_subsumes_a


def document(entry: Derived) -> dict[str, Json]:
    """An entry as the file and a case hold it."""
    # A counterexample may be null, so nothing is left out for being null.
    return {direction: evidence.model_dump() for direction, evidence in by_label(entry)}


class Derivations(DerivedSpec):
    """``derived.json``, with what its schema cannot say."""

    @model_validator(mode="after")
    def _an_entry_shows_a_label_and_an_agreement_is_of_different_checkers(self) -> Self:
        for case, entry in self.cases.items():
            if not list(by_label(entry)):
                raise ValueError(f"{case}: shows no label")
            for direction, evidence in by_label(entry):
                if not isinstance(evidence, Agreement):
                    continue
                names = Counter(checker.rpartition(" ")[0] for checker in evidence.checkers)
                if len(names) < 2:
                    raise ValueError(f"{case}: {direction} rests on one checker, {sorted(names)}")
        return self

    @staticmethod
    def write(path: Path, cases: Mapping[str, Derived]) -> None:
        """Write the file with one case on a line, sorted, and every non-ASCII character escaped."""
        lines = [
            f"    {json.dumps(case)}: {json.dumps(document(cases[case]), allow_nan=False)}"
            for case in sorted(cases, key=lambda case: case.split("/"))
        ]
        listed = "{\n" + ",\n".join(lines) + "\n  }" if lines else "{}"
        path.write_text(
            f'{{\n  "$schema": "./schemas/derived.schema.json",\n  "cases": {listed}\n}}\n',
            encoding="utf-8",
        )
