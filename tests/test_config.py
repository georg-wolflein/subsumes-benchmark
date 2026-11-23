"""The configuration files are what the models generated from their schemas say."""

from reading import ROOT
from subsumes_benchmark.build import Collections
from subsumes_benchmark.generated.collections import FromGenerator, FromSource


def test_the_collections_are_read() -> None:
    config = Collections.read(ROOT / "collections.json")
    specs = config.collections.values()
    sourced = {spec.built_from.name for spec in specs if isinstance(spec.built_from, FromSource)}
    assert sourced == set(config.sources)
    # A collection is read from a source or built by a generator, and the model tells which.
    assert {type(spec.built_from) for spec in specs} == {FromSource, FromGenerator}
