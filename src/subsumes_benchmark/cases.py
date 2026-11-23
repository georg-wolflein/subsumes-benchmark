"""Reading a case of the corpus: one read from an upstream source, or one that is generated.

``case.schema.json`` says that a case is one of the two, told apart by its ``kind``, and the
model of the union is generated from it with ``kind`` as its discriminator. So a case is
checked against the one model that it says it is.
"""

from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from subsumes_benchmark.config import ConfigError
from subsumes_benchmark.generated.case import CaseSpec, GeneratedCase, UpstreamCase

_CASE: TypeAdapter[UpstreamCase | GeneratedCase] = TypeAdapter(CaseSpec)


def read_case(path: Path) -> UpstreamCase | GeneratedCase:
    """The case that a file of the corpus holds."""
    try:
        return _CASE.validate_json(path.read_bytes())
    except FileNotFoundError as error:
        raise ConfigError(f"{path} does not exist") from error
    except ValidationError as error:
        raise ConfigError(f"{path}: {error}") from error
