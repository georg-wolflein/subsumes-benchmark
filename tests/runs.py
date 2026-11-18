"""Runs and results as the tests make them."""

import json
from typing import TYPE_CHECKING, Literal, assert_never

from pydantic import TypeAdapter

from subsumes_benchmark.compare.results import Ending, Result, Run, result_line, write_run
from subsumes_benchmark.generated.result import Checked, ResultSpec, Unchecked, Witness

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from subsumes_benchmark import Json
    from subsumes_benchmark.generated.result import Direction

type Confirmation = Literal["confirmed", "not_an_instance", "accepted", "unchecked"]

_RESULT: TypeAdapter[Result] = TypeAdapter(ResultSpec)


def a_run(
    name: str = "one", label: str = "One", variant: str | None = None, corpus: str = "v1.0.0"
) -> Run:
    checker: dict[str, Json] = {
        "$schema": "../../schemas/checker.schema.json",
        "label": label,
        "version": "1.0",
        "homepage": "https://example.com",
        "dialect": "2020-12",
        "build": ["true"],
        "run": ["true"],
    }
    if variant is not None:
        checker["variant"] = variant
    run: dict[str, Json] = {
        "name": name,
        "checker": checker,
        "corpus": corpus,
        "timeout": 10.0,
        "warmup": 0,
        "seed": 0,
        "jobs": 1,
        "tasks": 0,
        "platform": "a machine",
        "processor": "a processor",
        "started": "2026-01-01T00:00:00+00:00",
        "wall_seconds": 1.0,
    }
    return Run.model_validate_json(json.dumps(run))


def a_witness(
    confirmation: Confirmation, counterexample: Json = 1, message: str = "why"
) -> Witness:
    if confirmation == "unchecked":
        return Unchecked(counterexample=counterexample, confirmation="unchecked", message=message)
    return Checked(counterexample=counterexample, confirmation=confirmation)


def a_result(
    case: str,
    ended: Ending,
    expected: bool | None,
    *,
    seconds: float = 0.001,
    direction: Direction = "a_subsumes_b",
    reason: str | None = None,
    message: str | None = None,
    witness: Witness | None = None,
) -> Result:
    """A result that ended so, with the keys of that ending and none that are not given."""
    said: dict[str, object] = {"case": case, "direction": direction, "expected": expected}
    timed = {"seconds": seconds, "wall_seconds": seconds}
    match ended:
        case "yes":
            said |= {"answer": True, **timed}
        case "no":
            said |= {"answer": False, **timed}
            if witness is not None:
                said["witness"] = witness
        case "unknown":
            said |= {"answer": None, **timed}
            if reason is not None:
                said["reason"] = reason
        case "error":
            said |= {"failure": "error", **timed}
        case "timeout":
            said |= {"failure": "timeout", "wall_seconds": seconds}
        case "unsupported":
            said |= {"failure": "unsupported"}
        case "crash":
            said |= {"failure": "crash", "wall_seconds": seconds}
        case _:
            assert_never(ended)
    if message is not None:
        said["message"] = message
    elif ended in ("error", "unsupported", "crash"):
        said["message"] = f"an {ended}"
    return _RESULT.validate_python(said)


def write(folder: Path, run: Run, results: Sequence[Result]) -> None:
    folder.mkdir(parents=True)
    write_run(folder, run)
    (folder / "results.jsonl").write_text("".join(map(result_line, results)), encoding="utf-8")
