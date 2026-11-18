# /// script
# requires-python = "==3.14.*"
# dependencies = ["subsumes==0.4.0"]
# ///
"""The adapter for subsumes's Python package: answers the runner's requests, one JSON line each.

"A accepts every instance of B" is the library's own question, with the two schemas in that
order. The library always asserts ``format``, so there is nothing to set for it. The package
wraps the Rust library, so the answers are those of ``checkers/subsumes`` and the time adds
what the binding costs.
"""

import json
import sys
import time
from typing import assert_never

from subsumes import Budget, Json, No, Reason, Unknown, Unrepresentable, Unsupported, Yes, subsumes


def kind(reason: Reason) -> str:
    """What a report counts the declined tasks by, as ``checkers/subsumes`` names it."""
    match reason:
        case Budget():
            return "budget"
        case Unrepresentable():
            return "unrepresentable instance"
        case Unsupported(location=location):
            # The location is a URI reference whose fragment is a JSON Pointer, and the last
            # token of the pointer names the keyword.
            pointer = location.partition("#")[2]
            if "/" not in pointer:
                return "whole schema"
            return pointer.rpartition("/")[2].replace("~1", "/").replace("~0", "~")
        case _:
            assert_never(reason)


def check(request: str) -> dict[str, Json]:
    """The reply to a request, without its time."""
    try:
        # The package takes a schema as ``json.loads`` gives it, which is how the request
        # holds the two, and checks with the default work budget.
        schemas = json.loads(request)
        verdict = subsumes(schemas["a"], schemas["b"])
    except Exception as exc:
        return {"failure": "error", "message": f"{type(exc).__name__}: {exc}"[:300]}
    match verdict:
        case Yes():
            return {"answer": True}
        case No(counterexample):
            return {"answer": False, "counterexample": counterexample}
        case Unknown(reason):
            # A check that spends its work budget ends here too, and the reason says so.
            return {"answer": None, "reason": kind(reason), "message": str(reason)[:300]}


def main() -> None:
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        # The clock runs from the request as text to the answer, so that each schema is
        # parsed once in that time. The runner enforces the timeout.
        start = time.perf_counter()
        reply = check(line)
        seconds = time.perf_counter() - start
        print(json.dumps({**reply, "seconds": seconds}), flush=True)


main()
