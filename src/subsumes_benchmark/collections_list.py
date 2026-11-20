"""The list of the collections of a corpus, as Markdown.

``python -m subsumes_benchmark.collections_list <corpus>`` prints it. ``make corpus`` puts it
into the README of the repository, with ``scripts/readme_part.py``.
"""

import json
import sys
from pathlib import Path

from subsumes_benchmark.build import MANIFEST_NAME

# Where the corpus lies in the repository. The README is the page of the package on PyPI too,
# so a link in it is a full URL.
CORPUS_URL = "https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus"


def collections_list(corpus: Path) -> str:
    """The list of the collections of a corpus, as the README of the repository shows it.

    An item names a collection as a link to its folder, and has what ``collections.json`` of
    the corpus says about it, how many cases it has, and how many of its tasks have a label:
    a case is two tasks, one for each direction. A line after the list has the sums.
    """
    manifest = json.loads((corpus / MANIFEST_NAME).read_text(encoding="utf-8"))
    items = []
    cases = labelled = 0
    for folder, collection in manifest.items():
        files = sorted((corpus / folder).glob("*.json"))
        known = 0
        for file in files:
            case = json.loads(file.read_text(encoding="utf-8"))
            known += (case["a_subsumes_b"] is not None) + (case["b_subsumes_a"] is not None)
        origin = collection["origin"]
        items.append(
            f"- **[`{folder}`]({CORPUS_URL}/{folder})**: {collection['description']} "
            f"From [{origin['short']}]({origin['url']}). "
            f"{len(files):,} cases, {known:,} of {2 * len(files):,} tasks with a label."
        )
        cases += len(files)
        labelled += known
    total = f"In all: {cases:,} cases, {labelled:,} of {2 * cases:,} tasks with a label."
    return "\n".join([*items, "", total])


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m subsumes_benchmark.collections_list <corpus>")
    print(collections_list(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
