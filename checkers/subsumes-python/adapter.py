# /// script
# requires-python = "==3.14.*"
# dependencies = ["subsumes==0.2.0"]
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
from pathlib import Path

from subsumes import No, UndecidedError, Yes, subsumes


def check(a: str, b: str) -> tuple[str, str | None]:
    try:
        # The package takes a schema as ``json.loads`` gives it, with the default work budget.
        verdict = subsumes(json.loads(a), json.loads(b))
    except UndecidedError as exc:
        # A check that spends its work budget ends here too, and the message says so.
        return "unknown", str(exc)[:300]
    except Exception as exc:
        return "error", f"{type(exc).__name__}: {exc}"[:300]
    match verdict:
        case Yes():
            return "yes", None
        case No(counterexample):
            return "no", json.dumps(counterexample)[:300]


def main() -> None:
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        request = json.loads(line)
        a = Path(request["a"]).read_text(encoding="utf-8")
        b = Path(request["b"]).read_text(encoding="utf-8")
        # The clock runs from the schemas as text to the answer. The runner enforces the
        # timeout.
        start = time.perf_counter()
        answer, detail = check(a, b)
        seconds = time.perf_counter() - start
        print(json.dumps({"answer": answer, "seconds": seconds, "detail": detail}), flush=True)


main()
