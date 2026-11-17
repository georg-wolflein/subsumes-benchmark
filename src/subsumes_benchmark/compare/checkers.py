"""A checker under ``checkers/`` and the process that answers for it.

Every checker is driven through an adapter: a program that starts once, prints
``{"ready": true}`` and then answers one request per line on its standard input with one
line on its standard output. ``checkers/README.md`` has the protocol.
"""

import contextlib
import json
import os
import selectors
import signal
import subprocess
import time
import tomllib
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING, Literal, Self, cast, get_args

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from subsumes_benchmark.compare.results import Answer

type Dialect = Literal["2020-12", "draft-07", "draft-04"]
DIALECTS: Sequence[Dialect] = get_args(Dialect.__value__)

type AdapterAnswer = Literal["yes", "no", "unknown", "error", "timeout"]
ADAPTER_ANSWERS: Sequence[AdapterAnswer] = get_args(AdapterAnswer.__value__)

# How long an adapter may take to start, which for some includes starting a JVM.
STARTUP_SECONDS = 300.0
# How much longer than the timeout the runner waits before it kills the process. An adapter
# that stops a check itself stays alive, and warm, if it reports the timeout in this time.
GRACE_SECONDS = 2.0


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Checker:
    """A checker as its ``checker.toml`` describes it."""

    name: str
    folder: Path
    label: str
    # What tells this checker from another one of the same label, such as the language of
    # the package it is used through.
    variant: str | None
    version: str
    homepage: str
    dialect: Dialect
    build: Sequence[str]
    run: Sequence[str]

    @classmethod
    def load(cls, folder: Path) -> Self:
        path = folder / "checker.toml"
        if not path.is_file():
            raise ConfigError(f"{path} does not exist")
        spec = tomllib.loads(path.read_text(encoding="utf-8"))
        dialect = spec["dialect"]
        if dialect not in DIALECTS:
            raise ConfigError(f"{path}: dialect is {dialect!r}, not one of {list(DIALECTS)}")
        return cls(
            name=folder.name,
            folder=folder,
            label=spec["label"],
            variant=spec.get("variant"),
            version=spec["version"],
            homepage=spec["homepage"],
            dialect=dialect,
            build=spec["build"],
            run=spec["run"],
        )

    def compile(self) -> None:
        """Build the adapter, in its folder."""
        subprocess.run(self.build, cwd=self.folder, check=True)


@dataclass(frozen=True)
class Reply:
    """What came back for one request."""

    answer: Answer
    seconds: float | None
    wall_seconds: float
    detail: str | None = None


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

    def ask(self, a: Path, b: Path, timeout: float) -> Reply:
        """Ask whether ``a`` accepts every instance valid under ``b``."""
        try:
            process = self._started()
        except (_TimedOutError, _DiedError) as exc:
            self._kill()
            return Reply("crash", None, 0.0, f"the adapter did not start: {exc}")
        request = json.dumps({"a": str(a), "b": str(b), "timeout": timeout}) + "\n"
        start = time.perf_counter()
        try:
            assert process.stdin is not None
            process.stdin.write(request.encode())
            process.stdin.flush()
            line = self._line(start + timeout + GRACE_SECONDS)
        except _TimedOutError:
            self._kill()
            return Reply("timeout", None, time.perf_counter() - start)
        except (_DiedError, BrokenPipeError) as exc:
            self._kill()
            return Reply("crash", None, time.perf_counter() - start, str(exc) or None)
        wall = time.perf_counter() - start
        try:
            reply = json.loads(line)
            answer, seconds, detail = reply["answer"], reply.get("seconds"), reply.get("detail")
            if answer not in ADAPTER_ANSWERS:
                raise ValueError(answer)
            if seconds is not None:
                seconds = float(seconds)
        except ValueError, KeyError, TypeError:
            # The adapter and the runner no longer agree on where a reply ends.
            self._kill()
            return Reply("crash", None, wall, f"not a reply: {line[:200]!r}")
        answer = cast("AdapterAnswer", answer)
        if answer == "timeout" or (seconds is not None and seconds > timeout):
            return Reply("timeout", None, wall)
        return Reply(answer, seconds, wall, None if detail is None else str(detail)[:500])

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
        ready = json.loads(self._line(time.perf_counter() + STARTUP_SECONDS))
        if not (isinstance(ready, dict) and ready.get("ready") is True):
            raise _DiedError(f"expected the ready line, got {ready!r}")
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
