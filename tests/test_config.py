"""The configuration files are what their models say, and the schemas are those of the models."""

from reading import ROOT, read
from subsumes_benchmark.build import Collections
from subsumes_benchmark.schemas import MODELS, schema_of

SCHEMAS = ROOT / "schemas"


def test_the_committed_schemas_are_those_of_the_models() -> None:
    assert {path.name for path in SCHEMAS.iterdir()} == set(MODELS)
    stale = [name for name in MODELS if read(SCHEMAS / name) != schema_of(name)]
    assert stale == [], "run `make schemas`"


def test_the_collections_are_read() -> None:
    config = Collections.read(ROOT / "collections.json")
    assert {spec.source for spec in config.collections.values()} == set(config.sources)
