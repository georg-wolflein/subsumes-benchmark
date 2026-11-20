"""What the README of the repository says about a corpus, as Markdown.

``python -m subsumes_benchmark.readme_parts <corpus> <part>`` prints one part: the list of
the collections, how many collections there are, or how many tasks have a label. ``make
corpus`` puts each into the README, with ``scripts/readme_part.py``.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self, assert_never

from subsumes_benchmark.build import MANIFEST_NAME

if TYPE_CHECKING:
    from collections.abc import Sequence

# Where the corpus lies in the repository. The README is the page of the package on PyPI too,
# so a link in it is a full URL.
CORPUS_URL = "https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus"

type Part = Literal["collections", "num_collections", "num_labelled_tasks"]
"""A part of the README that the corpus decides, by the name of its markers."""


@dataclass(frozen=True)
class Collection:
    """What the README says about one collection of a corpus."""

    folder: str
    description: str
    # The work that first published the pairs, as a short name and where to read it.
    origin: str
    origin_url: str
    cases: int
    # How many of its tasks have a label. A case is two tasks, one for each direction.
    labelled: int

    @classmethod
    def read_all(cls, corpus: Path) -> Sequence[Self]:
        """The collections of a corpus, in the order of its ``collections.json``."""
        manifest = json.loads((corpus / MANIFEST_NAME).read_text(encoding="utf-8"))
        collections = []
        for folder, collection in manifest.items():
            files = sorted((corpus / folder).glob("*.json"))
            labelled = 0
            for file in files:
                case = json.loads(file.read_text(encoding="utf-8"))
                labelled += (case["a_subsumes_b"] is not None) + (case["b_subsumes_a"] is not None)
            origin = collection["origin"]
            collections.append(
                cls(
                    folder=folder,
                    description=collection["description"],
                    origin=origin["short"],
                    origin_url=origin["url"],
                    cases=len(files),
                    labelled=labelled,
                )
            )
        return collections


def collections_list(collections: Sequence[Collection]) -> str:
    """The list of the collections, as the README of the repository shows it.

    An item names a collection as a link to its folder, and has what ``collections.json`` of
    the corpus says about it, how many cases it has, and how many of its tasks have a label.
    A line after the list has the sums.
    """
    items = [
        f"- **[`{c.folder}`]({CORPUS_URL}/{c.folder})**: {c.description} "
        f"From [{c.origin}]({c.origin_url}). "
        f"{c.cases:,} cases, {c.labelled:,} of {2 * c.cases:,} tasks with a label."
        for c in collections
    ]
    cases = sum(c.cases for c in collections)
    labelled = sum(c.labelled for c in collections)
    total = f"In all: {cases:,} cases, {labelled:,} of {2 * cases:,} tasks with a label."
    return "\n".join([*items, "", total])


def readme_part(corpus: Path, part: Part) -> str:
    """One part of the README, from the corpus in a folder."""
    collections = Collection.read_all(corpus)
    match part:
        case "collections":
            return collections_list(collections)
        case "num_collections":
            return f"{len(collections):,}"
        case "num_labelled_tasks":
            return f"{sum(c.labelled for c in collections):,}"
        case _:
            assert_never(part)


def main() -> None:
    match sys.argv[1:]:
        case [corpus, "collections" | "num_collections" | "num_labelled_tasks" as part]:
            print(readme_part(Path(corpus), part))
        case _:
            sys.exit(
                "usage: python -m subsumes_benchmark.readme_parts <corpus> "
                "collections|num_collections|num_labelled_tasks"
            )


if __name__ == "__main__":
    main()
