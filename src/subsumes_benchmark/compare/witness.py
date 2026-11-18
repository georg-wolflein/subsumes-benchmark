"""Whether the counterexample of a no is one.

A checker may give a counterexample with a no: an instance that is valid under the schema
whose instances were to be accepted and invalid under the schema that was to accept them.
That can be checked without a label, by a validator. The validator is ``jsonschema-rs``, which
reads a schema as the labels of the corpus do: as draft 2020-12, with ``format`` asserted and
every pattern as one of ECMA-262. It is asked about the two schemas of the case as the corpus
has them, also where the checker reads an older draft and got them rewritten.

Numbers are read as most parsers of JSON read them: a whole number that 64 bits do not hold
is the double nearest to it. Python keeps every digit of such a number, and the validator
would then tell it from the double that a checker gives for it. The corpus has no case that
turns on digits that a double does not hold.
"""

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, assert_never, cast

from jsonschema_rs import Draft202012Validator, ValidationError

if TYPE_CHECKING:
    from subsumes_benchmark import Json
    from subsumes_benchmark.compare.tasks import Direction
    from subsumes_benchmark.generated.case import CaseSpec, Schema

type Confirmation = Literal["confirmed", "not_an_instance", "accepted", "unchecked"]
"""What the validator makes of a counterexample.

- ``confirmed``: it is valid under the one schema and invalid under the other, as it has to be.
- ``not_an_instance``: the schema whose instances were to be accepted rejects it, so the other
  schema did not have to accept it.
- ``accepted``: the schema that was to accept it does, so it tells the two apart in nothing.
- ``unchecked``: the validator did not look at it; the note of the witness says why.
"""


@dataclass(frozen=True)
class Witness:
    """The counterexample that a checker gave with a no, and what the validator made of it."""

    instance: Json
    confirmation: Confirmation
    note: str | None = None

    @property
    def refuted(self) -> bool:
        """Whether the validator found that the counterexample is none."""
        return self.confirmation in ("not_an_instance", "accepted")


class _NoNumberError(Exception):
    """A value holds a number that is none in JSON, or one that no double is near."""


def _validator(schema: Schema) -> Draft202012Validator:
    # Nothing is fetched: a schema of the corpus carries what it references.
    read = cast("Schema", _read(schema))
    return Draft202012Validator(read, validate_formats=True, offline=True)


def _read(value: Json) -> Json:
    """The value with its numbers as a parser of 64 bits reads them.

    A whole number from -2^63 to 2^64 - 1 is kept, and any other becomes the double nearest
    to it.

    Raises:
        _NoNumberError: A number is infinite or not a number, which Python's parser gives for
            text that is no JSON, or is a whole number beyond every double.
    """
    match value:
        case bool():
            return value
        case int():
            if -(2**63) <= value < 2**64:
                return value
            try:
                return float(value)
            except OverflowError as error:
                raise _NoNumberError from error
        case float():
            if not math.isfinite(value):
                raise _NoNumberError
            return value
        case list():
            return [_read(item) for item in value]
        case dict():
            return {name: _read(item) for name, item in value.items()}
        case _:
            return value


def confirm(case: CaseSpec, direction: Direction, instance: Json) -> Witness:
    """Ask the validator about the counterexample of a no to one task of the case."""
    match direction:
        case "a_subsumes_b":
            accepting, accepted = case.a, case.b
        case "b_subsumes_a":
            accepting, accepted = case.b, case.a
        case _:
            assert_never(direction)
    try:
        read = _read(instance)
    except _NoNumberError:
        # The instance is not kept: a results file could not hold such a number either.
        return Witness(None, "unchecked", "the counterexample holds a number that is none in JSON")
    try:
        wide, narrow = _validator(accepting), _validator(accepted)
    except ValidationError as error:
        refusal = str(error).partition("\n")[0]
        return Witness(instance, "unchecked", f"the validator does not take a schema: {refusal}")
    except _NoNumberError:
        return Witness(instance, "unchecked", "a schema holds a number that no double is near")
    if not narrow.is_valid(read):
        return Witness(instance, "not_an_instance")
    if wide.is_valid(read):
        return Witness(instance, "accepted")
    return Witness(instance, "confirmed")
