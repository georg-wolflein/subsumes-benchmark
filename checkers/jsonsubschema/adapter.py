# /// script
# requires-python = "==3.14.*"
# dependencies = ["jsonsubschema==0.0.8"]
# ///
"""The adapter for jsonsubschema: answers the runner's requests, one JSON line each.

jsonsubschema reads draft-04, so the runner hands it schemas rewritten to that draft.
``isSubschema(b, a)`` asks whether every instance of B is an instance of A.
"""

import json
import os
import signal
import sys
import time

# The library prints while it works; the runner owns the standard output.
protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8")
os.dup2(sys.stderr.fileno(), sys.stdout.fileno())

from jsonsubschema import isSubschema  # noqa: E402


class TimedOutError(Exception):
    pass


def on_alarm(signum: int, frame: object) -> None:
    raise TimedOutError


TIMEOUT: dict[str, object] = {"failure": "timeout"}


def failed(message: str) -> dict[str, object]:
    return {"failure": "error", "message": message}


def check(a: object, b: object) -> dict[str, object]:
    """The reply without its time."""
    try:
        # Anything but ``True`` is a no: some of the library's paths fall through to ``None``.
        return {"answer": isSubschema(b, a) is True}
    except TimedOutError:
        return TIMEOUT
    except RecursionError:
        return failed("RecursionError")
    except SystemExit:
        return failed("the library called sys.exit")  # it does where it sees no way on
    except Exception as exc:
        return failed(f"{type(exc).__name__}: {exc}"[:300])


def main() -> None:
    signal.signal(signal.SIGALRM, on_alarm)
    print(json.dumps({"ready": True}), file=protocol, flush=True)
    for line in sys.stdin:
        # The library takes a schema as ``json.loads`` gives it, which is how the request
        # holds the two. So the clock runs from the request as text to the answer: each
        # schema is parsed once in that time.
        start = time.perf_counter()
        request = json.loads(line)
        signal.setitimer(signal.ITIMER_REAL, request["timeout"])
        try:
            reply = check(request["a"], request["b"])
        except TimedOutError:  # the alarm went off between the check and here
            reply = TIMEOUT
        seconds = time.perf_counter() - start
        signal.setitimer(signal.ITIMER_REAL, 0)
        # A timeout has no time: the check did not end.
        if reply is not TIMEOUT:
            reply = {**reply, "seconds": seconds}
        print(json.dumps(reply), file=protocol, flush=True)


main()
