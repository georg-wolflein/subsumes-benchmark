"""The configuration files are what the models generated from their schemas say."""

from reading import ROOT
from subsumes_benchmark.build import Collections


def test_the_collections_are_read() -> None:
    config = Collections.read(ROOT / "collections.json")
    assert {spec.source for spec in config.collections.values()} == set(config.sources)
