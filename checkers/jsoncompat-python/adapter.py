# /// script
# requires-python = "==3.14.*"
# dependencies = ["jsoncompat==0.6.0"]
# ///
"""The adapter for jsoncompat's Python package: answers the runner's requests, one JSON line each.

"A accepts every instance of B" is jsoncompat's serializer role with A as the old schema and
B as the new one: every value the new schema produces must be accepted by the old. The package
wraps the Rust library, so the answers are those of ``checkers/jsoncompat`` and the time adds
what the binding costs.
"""

import json
import sys
import time

from jsoncompat import SchemaOptions, analyze_compat

# The corpus's labels hold with ``format`` asserted.
OPTIONS: SchemaOptions = {"assert_formats": True}


def check(a: str, b: str) -> dict[str, object]:
    """The reply without its time."""
    try:
        result = analyze_compat(a, b, "serializer", options=OPTIONS)
    except Exception as exc:
        return {"failure": "error", "message": f"{type(exc).__name__}: {exc}"[:300]}
    if result["status"] == "compatible":
        return {"answer": True}
    if result["status"] == "incompatible":
        return {"answer": False, "message": result["counterexample_json"][:300]}
    return {"answer": None, "message": result["reason"][:300]}


def main() -> None:
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        # The package takes a schema as text, so each is written back to text first.
        a, b = json.dumps(request["a"]), json.dumps(request["b"])
        # The clock runs from the schemas as text to the answer, so that each is parsed once
        # in that time. The call cannot be interrupted from Python, so the runner enforces
        # the timeout.
        start = time.perf_counter()
        reply = check(a, b)
        seconds = time.perf_counter() - start
        print(json.dumps({**reply, "seconds": seconds}), flush=True)


main()
