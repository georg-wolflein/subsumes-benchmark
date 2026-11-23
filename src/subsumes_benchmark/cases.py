"""Reading a case of the corpus: one read from an upstream source, or one that is generated.

``case.schema.json`` says that a case is one of the two, and the model of each is generated
from it. Which of them a case is shows in the one key that tells them apart: a case that says
what it was ``generated`` from is a generated case, and every other links to its ``upstream``
file. That key is the discriminator of the union, so a case is checked against the one model
that it claims to be.
"""

from pathlib import Path
from typing import Annotated

from pydantic import Discriminator, Tag, TypeAdapter, ValidationError

from subsumes_benchmark import Json
from subsumes_benchmark.config import ConfigError
from subsumes_benchmark.generated.case import GeneratedCase, UpstreamCase


def _kind(case: object) -> str:
    """Which of the two models a case is, as a document or as a model."""
    if isinstance(case, dict):
        return "generated" if "generated" in case else "upstream"
    return "generated" if isinstance(case, GeneratedCase) else "upstream"


type Case = Annotated[
    Annotated[UpstreamCase, Tag("upstream")] | Annotated[GeneratedCase, Tag("generated")],
    Discriminator(_kind),
]
"""A case of the corpus, as ``case.schema.json`` describes it."""

_CASE: TypeAdapter[UpstreamCase | GeneratedCase] = TypeAdapter(Case)


def read_case(path: Path) -> UpstreamCase | GeneratedCase:
    """The case that a file of the corpus holds."""
    try:
        return _CASE.validate_json(path.read_bytes())
    except FileNotFoundError as error:
        raise ConfigError(f"{path} does not exist") from error
    except ValidationError as error:
        raise ConfigError(f"{path}: {error}") from error


def parse_case(document: Json) -> UpstreamCase | GeneratedCase:
    """A case from what its file holds, as ``json.load`` gives it."""
    return _CASE.validate_python(document)
