"""The configuration files are what the models generated from their schemas say."""

from reading import ROOT
from subsumes_benchmark.build import Collections
from subsumes_benchmark.generated.collections import GeneratedCollection, SourceCollection


def test_the_collections_are_read() -> None:
    config = Collections.read(ROOT / "collections.json")
    specs = config.collections.values()
    sourced = {spec.source for spec in specs if isinstance(spec, SourceCollection)}
    assert sourced == set(config.sources)
    # A collection is read from a source or generated, and the model tells which.
    assert {type(spec) for spec in specs} == {SourceCollection, GeneratedCollection}
