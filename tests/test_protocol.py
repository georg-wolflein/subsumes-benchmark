"""The protocol between the runner and an adapter, and the files of a run and of a report.

The schemas under ``schemas/`` are written by hand and decide what a line or a file is. The
runner reads and writes with models that are generated from them, which read a little more
than the schemas allow: ``1`` for ``true``, and ``null`` for a key that is left out. Nothing
is made of that. What is held here is that the runner reads everything that a schema allows,
refuses what is plainly something else, and writes nothing that a schema does not allow.
"""

import json
import re
from typing import TYPE_CHECKING, cast

import pytest
from jsonschema_rs import Draft202012Validator
from pydantic import TypeAdapter, ValidationError

from reading import ROOT, read
from runs import a_result, a_run, a_witness, write
from subsumes_benchmark.compare.results import ENDINGS, Run, read_results, read_run
from subsumes_benchmark.compare.summary import Summary, read_entries
from subsumes_benchmark.generated.ready import ReadySpec
from subsumes_benchmark.generated.reply import ReplySpec
from subsumes_benchmark.generated.request import RequestSpec
from subsumes_benchmark.generated.result import ResultSpec

if TYPE_CHECKING:
    from pathlib import Path

    from subsumes_benchmark import Json

READERS: dict[str, TypeAdapter] = {
    "ready": TypeAdapter(ReadySpec),
    "request": TypeAdapter(RequestSpec),
    "reply": TypeAdapter(ReplySpec),
    "result": TypeAdapter(ResultSpec),
    "run": TypeAdapter(Run),
    "summary": TypeAdapter(Summary),
}


def written(name: str) -> dict[str, Json]:
    return cast("dict[str, Json]", read(ROOT / "schemas" / f"{name}.schema.json"))


def definitions(name: str) -> dict[str, dict[str, dict[str, Json]]]:
    """The definitions of a schema, each with its keywords."""
    return cast("dict[str, dict[str, dict[str, Json]]]", written(name)["$defs"])


def schema(name: str) -> Draft202012Validator:
    # A format is asserted, as it is for the schemas of the corpus: the time of a run is one.
    return Draft202012Validator(written(name), validate_formats=True)


def reads(name: str, document: Json) -> bool:
    """Whether the runner's model takes the document, as a line of JSON."""
    try:
        READERS[name].validate_json(json.dumps(document))
    except ValidationError:
        return False
    return True


TASK: dict[str, Json] = {"case": "c/1", "direction": "a_subsumes_b", "expected": None}
TIMED: dict[str, Json] = {"seconds": 0.001, "wall_seconds": 0.002}
A_RUN = json.loads(a_run(variant="Rust").model_dump_json(by_alias=True, exclude_unset=True))
A_SUMMARY: dict[str, Json] = {
    "corpus": "v1.0.0", "collections": 2, "cases": 3, "tasks": 6, "labelled_tasks": 5,
    "timeout": 10.0,
}  # fmt: skip

VALID: dict[str, list[Json]] = {
    "ready": [{"ready": True}],
    "request": [
        {"a": {"type": "string"}, "b": {"maxLength": 3}, "timeout": 10.0},
        {"a": True, "b": False, "timeout": 1},
    ],
    "reply": [
        {"answer": True, "seconds": 0.5},
        {"answer": True, "seconds": 0},
        {"answer": False, "seconds": 0.5},
        {"answer": False, "seconds": 0.5, "counterexample": None},
        {"answer": False, "seconds": 0.5, "counterexample": {"x": [1, 2.5]}, "message": "x"},
        {"answer": None, "seconds": 0.5},
        {"answer": None, "seconds": 0.5, "reason": "format", "message": "no format"},
        {"failure": "error", "message": "no schema"},
        {"failure": "error", "message": "no schema", "seconds": 0.5},
        {"failure": "timeout"},
    ],
    "result": [
        {**TASK, "answer": True, **TIMED},
        {**TASK, "expected": True, "answer": False, **TIMED, "message": "x"},
        {**TASK, "answer": False, **TIMED, "witness": {"counterexample": None, "confirmation": "confirmed"}},
        {**TASK, "answer": False, **TIMED, "witness": {"confirmation": "unchecked", "message": "why"}},
        {**TASK, "answer": None, **TIMED, "reason": "format", "message": "no format"},
        {**TASK, "failure": "error", "message": "no schema", "wall_seconds": 0.002},
        {**TASK, "failure": "error", "message": "no schema", **TIMED},
        {**TASK, "failure": "timeout", "wall_seconds": 10.5},
        {**TASK, "failure": "unsupported", "message": "no $dynamicRef in draft-07"},
        {**TASK, "failure": "crash", "message": "the adapter died", "wall_seconds": 0.0},
    ],
    "run": [A_RUN, {**A_RUN, "timeout": 10, "wall_seconds": 0, "jobs": 8}],
    "summary": [
        A_SUMMARY,
        {**A_SUMMARY, "corpus": "v1.0.0-3-gabc1234", "timeout": 1},
        {**A_SUMMARY, "collections": 0, "cases": 0, "tasks": 0, "labelled_tasks": 0},
    ],
}  # fmt: skip

# What is none, each with whether the runner reads it all the same.
INVALID: dict[str, list[tuple[Json, bool]]] = {
    "ready": [({"ready": False}, False), ({}, False), ({"ready": True, "version": 1}, False)],
    "request": [
        ({"a": {}, "b": {}}, False),
        ({"a": {}, "timeout": 10.0}, False),
        ({"a": {}, "b": {}, "timeout": 0}, False),
        ({"a": {}, "b": {}, "timeout": "10"}, False),
        # The text of a schema is a string, and no schema.
        ({"a": "{}", "b": {}, "timeout": 10.0}, False),
        ({"a": None, "b": {}, "timeout": 10.0}, False),
        ({"a": {}, "b": {}, "timeout": 10.0, "dialect": "2020-12"}, False),
    ],
    "reply": [
        # Neither an answer nor a failure, or one that an adapter cannot give.
        ({}, False),
        ({"seconds": 0.5}, False),
        ({"answer": "yes", "seconds": 0.5}, False),
        ({"failure": "crash", "message": "x"}, False),
        ({"failure": "unsupported", "message": "x"}, False),
        ({"answer": True, "failure": "timeout", "seconds": 0.5}, False),
        # An answer without its time, and an error without its message.
        ({"answer": True}, False),
        ({"answer": None}, False),
        ({"failure": "error"}, False),
        # A key of another answer, and a key of none.
        ({"answer": True, "seconds": 0.5, "counterexample": 1}, False),
        ({"answer": True, "seconds": 0.5, "reason": "format"}, False),
        ({"answer": True, "seconds": 0.5, "message": "said so"}, False),
        ({"answer": False, "seconds": 0.5, "reason": "format"}, False),
        ({"answer": None, "seconds": 0.5, "counterexample": 1}, False),
        ({"failure": "error", "message": "x", "counterexample": 1}, False),
        ({"failure": "timeout", "seconds": 10.5}, False),
        ({"answer": False, "seconds": 0.5, "counter_example": 1}, False),
        ({"answer": True, "seconds": 0.5, "steps": 7}, False),
        # A value of the wrong kind.
        ({"answer": True, "seconds": "0.5"}, False),
        ({"answer": True, "seconds": -1}, False),
        ({"answer": None, "seconds": 0.5, "reason": 1}, False),
        ("yes", False),
        ([{"answer": True, "seconds": 0.5}], False),
        # What the model reads all the same: a number for true, and null for a key left out.
        ({"answer": 1, "seconds": 0.5}, True),
        ({"answer": None, "seconds": 0.5, "reason": None, "message": None}, True),
        ({"failure": "error", "message": "x", "seconds": None}, True),
    ],
    "result": [
        ({"answer": True, **TIMED}, False),
        ({**TASK, "answer": True, "seconds": 0.001}, False),
        ({**TASK, "answer": "yes", **TIMED}, False),
        ({**TASK, "direction": "b_subsumes_b", "answer": True, **TIMED}, False),
        ({**TASK, "expected": "yes", "answer": True, **TIMED}, False),
        ({**TASK, "answer": True, **TIMED, "witness": {"counterexample": 1, "confirmation": "confirmed"}}, False),
        ({**TASK, "answer": False, **TIMED, "counterexample": 1}, False),
        ({**TASK, "answer": False, **TIMED, "witness": {"confirmation": "confirmed"}}, False),
        ({**TASK, "answer": False, **TIMED, "witness": {"counterexample": 1, "confirmation": "refuted"}}, False),
        ({**TASK, "answer": False, **TIMED, "witness": {"counterexample": 1, "confirmation": "unchecked"}}, False),
        ({**TASK, "failure": "unsupported", "message": "x", "wall_seconds": 0.0}, False),
        ({**TASK, "failure": "crash", "wall_seconds": 0.0}, False),
        ({**TASK, "failure": "timeout"}, False),
        ({**TASK, "answer": True, **TIMED, "steps": 7}, False),
        ({**TASK, "answer": False, **TIMED, "witness": None}, True),
    ],
    "run": [
        ({**A_RUN, "timeout": 0}, False),
        ({**A_RUN, "jobs": 0}, False),
        ({**A_RUN, "tasks": 1.5}, False),
        ({**A_RUN, "started": "yesterday"}, False),
        ({**A_RUN, "checker": {**A_RUN["checker"], "dialect": "draft-06"}}, False),
        ({**A_RUN, "checker": "one"}, False),
        ({**A_RUN, "label": "One"}, False),
        ({key: value for key, value in A_RUN.items() if key != "jobs"}, False),
    ],
    "summary": [
        ({**A_SUMMARY, "timeout": 0}, False),
        ({**A_SUMMARY, "tasks": -1}, False),
        ({**A_SUMMARY, "labelled_tasks": 2.5}, False),
        ({**A_SUMMARY, "collections": "2"}, False),
        ({**A_SUMMARY, "corpus": None}, False),
        ({**A_SUMMARY, "checkers": 7}, False),
        ({key: value for key, value in A_SUMMARY.items() if key != "cases"}, False),
    ],
}  # fmt: skip


def name(value: object) -> str:
    return json.dumps(value)[:70] if not isinstance(value, bool) else str(value)


@pytest.mark.parametrize(
    ("kind", "document"),
    [(kind, document) for kind, documents in VALID.items() for document in documents],
    ids=name,
)
def test_the_runner_reads_what_a_schema_allows(kind: str, document: Json) -> None:
    assert schema(kind).is_valid(document)
    assert reads(kind, document)


@pytest.mark.parametrize(
    ("kind", "document", "read"),
    [(kind, document, read) for kind, documents in INVALID.items() for document, read in documents],
    ids=name,
)
def test_what_a_schema_does_not_allow(kind: str, document: Json, read: bool) -> None:
    assert not schema(kind).is_valid(document)
    assert reads(kind, document) is read


def test_what_the_runner_writes_is_what_the_schemas_say(tmp_path: Path) -> None:
    request = RequestSpec(a={"const": 10**52 + 1, "title": "é "}, b=True, timeout=10.0)
    line = request.model_dump_json(ensure_ascii=True)
    assert "\n" not in line
    assert line.isascii()
    assert schema("request").is_valid(json.loads(line))
    assert json.loads(line)["a"]["const"] == 10**52 + 1

    # A result of each ending, with every key that it can have and with none of those that
    # it need not have.
    full = [
        a_result("c/yes", "yes", True),
        a_result("c/no", "no", False, message="x", witness=a_witness("confirmed", None)),
        a_result("c/unchecked", "no", None, witness=a_witness("unchecked")),
        a_result("c/unknown", "unknown", None, reason="format", message="no format"),
        *(a_result(f"c/{ended}", ended, None) for ended in ENDINGS),
    ]
    write(tmp_path / "one", a_run(variant="Rust"), full)
    write(tmp_path / "two", a_run(), [])
    lines = (tmp_path / "one" / "results.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(full)
    for line in lines:
        assert schema("result").is_valid(json.loads(line)), line
    # Null is written only where it is a value: for no label, for a checker that declined,
    # and for a counterexample that is null.
    assert [line for line in lines if "null" in line] == [
        '{"case":"c/no","direction":"a_subsumes_b","expected":false,"answer":false,'
        '"seconds":0.001,"message":"x","wall_seconds":0.001,'
        '"witness":{"counterexample":null,"confirmation":"confirmed"}}',
        *(line for line in lines if '"expected":null' in line),
    ]
    assert read_results(tmp_path / "one") == full
    for folder in ("one", "two"):
        run = json.loads((tmp_path / folder / "run.json").read_text(encoding="utf-8"))
        assert schema("run").is_valid(run), run
        assert "variant" in run["checker"] or folder == "two"
        assert read_run(tmp_path / folder).started.isoformat() == "2026-01-01T00:00:00+00:00"

    # The summary of a report, as the report writes it: every key, and a whole number where
    # the timeout is one.
    write(tmp_path / "three" / "one", a_run(), full)
    summary = Summary.of(read_entries(tmp_path / "three"))
    text = summary.model_dump_json(indent=2)
    assert schema("summary").is_valid(json.loads(text)), text
    assert Summary.model_validate_json(text) == summary
    assert json.loads(text) == {
        "corpus": "v1.0.0",
        "collections": 1,
        "cases": len({result.case for result in full}),
        "tasks": len(full),
        "labelled_tasks": 2,
        "timeout": 10.0,
    }


def test_what_two_schemas_share_is_written_the_same_in_both() -> None:
    reply, result = definitions("reply"), definitions("result")
    # A result that an adapter's reply led to has the keys of that reply. The counterexample
    # of a no is in its witness, with what the validator made of it.
    for ended in ("Yes", "No", "Unknown", "Error", "Timeout"):
        of_reply, of_result = reply[ended]["properties"], result[ended]["properties"]
        added = {"wall_seconds", "witness"} if ended == "No" else {"wall_seconds"}
        moved = {"counterexample"} if ended == "No" else set()
        assert set(of_result) - set(of_reply) == added, ended
        assert set(of_reply) - set(of_result) == moved, ended
        for key in set(of_reply) - moved:
            assert of_result[key] == of_reply[key], (ended, key)
    # A summary says of the corpus and of the timeout what a run says of them.
    run_keys, summary_keys = written("run")["properties"], written("summary")["properties"]
    for key in ("corpus", "timeout"):
        assert cast("dict[str, Json]", summary_keys)[key] == cast("dict[str, Json]", run_keys)[key]
    # A run holds the checker as its file describes it.
    checker, run = written("checker"), definitions("run")
    for key in ("description", "type", "required", "additionalProperties", "properties"):
        assert run["Checker"][key] == checker[key], key
    for key, definition in definitions("checker").items():
        assert run[key] == definition, key
    # The directions of a result are the two labels of a case.
    labels = [
        key for key in cast("dict[str, Json]", written("case")["properties"]) if "_subsumes_" in key
    ]
    assert result["Direction"]["enum"] == labels


def test_the_examples_of_the_documentation_are_what_the_schemas_say() -> None:
    for page in ("checkers/README.md",):
        text = (ROOT / page).read_text(encoding="utf-8")
        lines = [
            json.loads(line)
            for block in re.findall(r"```json\n(.*?)```", text, flags=re.DOTALL)
            for line in block.splitlines()
            if line.startswith(('{"answer"', '{"failure"', '{"a"', '{"ready"'))
        ]
        kinds = {
            "ready": [line for line in lines if "ready" in line],
            "request": [line for line in lines if "a" in line],
            "reply": [line for line in lines if "answer" in line or "failure" in line],
        }
        assert kinds["request"], page
        assert kinds["reply"], page
        for kind, examples in kinds.items():
            assert all(schema(kind).is_valid(line) for line in examples), (page, kind)
