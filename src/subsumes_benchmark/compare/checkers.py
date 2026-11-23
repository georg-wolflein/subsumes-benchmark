"""A checker under ``checkers/`` and the process that answers for it.

Every checker is driven through an adapter: a program that starts once, prints
``{"ready": true}`` and then answers one request per line on its standard input with one
line on its standard output. ``checkers/README.md`` has the protocol, and the schemas
``ready``, ``request`` and ``reply`` under ``schemas/`` say what each line holds: the models
that write a request and read the other two are generated from those.
"""

import contextlib
import json
import os
import selectors
import signal
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Self, get_args

from pydantic import PrivateAttr, TypeAdapter, ValidationError

from subsumes_benchmark.generated.checker import CheckerSpec, Dialect
from subsumes_benchmark.generated.ready import ReadySpec
from subsumes_benchmark.generated.reply import ReplySpec, Timeout
from subsumes_benchmark.generated.request import RequestSpec, Schema

DIALECTS: Sequence[Dialect] = get_args(Dialect.__value__)

_REPLY: TypeAdapter[ReplySpec] = TypeAdapter(ReplySpec)
# The class of each of the five that a reply can be, by the value of the key that tells them
# apart: `answer` for the first three, `failure` for the others.
_ANSWERS = {True: "Yes", False: "No", None: "Unknown"}
_FAILURES = {"error": "Error", "timeout": "Timeout"}

# How long an adapter may take to start, which for some includes starting a JVM.
STARTUP_SECONDS = 300.0
# How much longer than the timeout the runner waits before it kills the process. An adapter
# that stops a check itself stays alive, and warm, if it reports the timeout in this time.
GRACE_SECONDS = 2.0


class Checker(CheckerSpec):
    """A checker of the comparison, and the folder under ``checkers/`` that holds its adapter."""

    _folder: Path = PrivateAttr()

    @classmethod
    def load(cls, folder: Path) -> Self:
        checker = cls.read(folder / "checker.json")
        checker._folder = folder
        return checker

    @property
    def folder(self) -> Path:
        return self._folder

    @property
    def name(self) -> str:
        return self._folder.name

    def compile(self) -> None:
        """Build the adapter, in its folder."""
        subprocess.run(self.build, cwd=self.folder, check=True)


@dataclass(frozen=True)
class Crashed:
    """The adapter is at fault: its process died or did not start, or a line of it is no reply."""

    message: str


def _fault(line: bytes, error: ValidationError) -> str:
    """What is wrong with a line that is no reply.

    A reply is one of five, and the line fails to be each of them. What is said is why it is
    not the one that its ``answer`` or its ``failure`` says it means to be.
    """
    try:
        document = json.loads(line)
    except ValueError:
        return "it is no JSON"
    if not isinstance(document, dict):
        return "it is no object"
    try:
        if "failure" in document:
            meant = _FAILURES.get(document["failure"])
        elif "answer" in document:
            meant = _ANSWERS.get(document["answer"])
        else:
            return "it has neither an answer nor a failure"
    except TypeError:  # a value that is no key of a dictionary, such as a list
        meant = None
    if meant is None:
        return "an answer is true, false or null, and a failure is error or timeout"
    faults = [e for e in error.errors() if e["loc"] and e["loc"][0] == meant]
    return "; ".join(f"{'.'.join(map(str, e['loc'][1:]))}: {e['msg']}" for e in faults)


class _TimedOutError(Exception):
    pass


class _DiedError(Exception):
    pass


class Worker:
    """One running adapter. It is started on the first request and again after it dies."""

    def __init__(self, checker: Checker, log: IO[bytes]) -> None:
        self.checker = checker
        self.log = log
        self.restarts = 0
        self._process: subprocess.Popen[bytes] | None = None
        self._buffer = b""

    def ask(self, a: Schema, b: Schema, timeout: float) -> tuple[ReplySpec | Crashed, float]:
        """Ask whether the schema ``a`` accepts every instance valid under the schema ``b``.

        The two go into the request as they are, as JSON values, on its one line.

        Returns:
            The reply, or that the adapter is at fault, and the seconds that the runner
            waited. A reply that came too late, and one that did not come, is a timeout.
        """
        try:
            process = self._started()
        except (_TimedOutError, _DiedError) as exc:
            self._kill()
            return Crashed(f"the adapter did not start: {exc}"), 0.0
        # In ASCII, so that an adapter reads the line the same whatever it takes its
        # standard input to be encoded in.
        request = RequestSpec(a=a, b=b, timeout=timeout).model_dump_json(ensure_ascii=True) + "\n"
        start = time.perf_counter()
        try:
            assert process.stdin is not None
            # A request holds two schemas and may be longer than a pipe takes at once.
            unsent = memoryview(request.encode())
            while unsent:
                unsent = unsent[process.stdin.write(unsent) :]
            process.stdin.flush()
            line = self._line(start + timeout + GRACE_SECONDS)
        except _TimedOutError:
            self._kill()
            return Timeout(failure="timeout"), time.perf_counter() - start
        except (_DiedError, BrokenPipeError) as exc:
            self._kill()
            return Crashed(str(exc) or "the adapter died"), time.perf_counter() - start
        wall = time.perf_counter() - start
        try:
            reply = _REPLY.validate_json(line)
        except ValidationError as error:
            # The adapter and the runner no longer agree on what a reply is, or on where
            # one ends.
            self._kill()
            return Crashed(f"not a reply ({_fault(line, error)}): {line[:200]!r}"), wall
        # An adapter that cannot stop a check may still reply after the time.
        seconds = None if isinstance(reply, Timeout) else reply.seconds
        if seconds is not None and seconds > timeout:
            return Timeout(failure="timeout"), wall
        return reply, wall

    def close(self) -> None:
        self._kill()

    def _started(self) -> subprocess.Popen[bytes]:
        if self._process is not None:
            return self._process
        self._buffer = b""
        self._process = subprocess.Popen(
            self.checker.run,
            cwd=self.checker.folder,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            bufsize=0,
            start_new_session=True,  # so that killing reaches what the command started
        )
        self.restarts += 1
        line = self._line(time.perf_counter() + STARTUP_SECONDS)
        try:
            ReadySpec.model_validate_json(line)
        except ValidationError as error:
            raise _DiedError(f"expected the ready line, got {line[:200]!r}") from error
        return self._process

    def _line(self, deadline: float) -> bytes:
        """The next line of the adapter's output, without its newline."""
        process = self._process
        assert process is not None
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b"\n" not in self._buffer:
                remaining = deadline - time.perf_counter()
                if remaining <= 0 or not selector.select(remaining):
                    raise _TimedOutError("no answer in time")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    code = process.wait()
                    raise _DiedError(f"the adapter exited with status {code}")
                self._buffer += chunk
        line, _, self._buffer = self._buffer.partition(b"\n")
        return line

    def _kill(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()
