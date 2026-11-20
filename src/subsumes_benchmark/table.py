"""The table of the collections of a corpus, as Markdown.

``python -m subsumes_benchmark.table <corpus>`` prints it. ``make corpus`` puts it into the
README of the repository, with ``scripts/readme-part.sh``.
"""

import json
import sys
from pathlib import Path

from subsumes_benchmark.build import MANIFEST_NAME


def collections_table(corpus: Path) -> str:
    """The table of the collections of a corpus, as the README of the repository shows it.

    A row has what ``collections.json`` of the corpus says about a collection, how many
    cases it has, and how many of its tasks have a label: a case is two tasks, one for each
    direction.
    """
    manifest = json.loads((corpus / MANIFEST_NAME).read_text(encoding="utf-8"))
    lines = [
        "| Collection | Cases | Tasks with a label | From | Content |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    cases = labelled = 0
    for folder, collection in manifest.items():
        files = sorted((corpus / folder).glob("*.json"))
        known = 0
        for file in files:
            case = json.loads(file.read_text(encoding="utf-8"))
            known += (case["a_subsumes_b"] is not None) + (case["b_subsumes_a"] is not None)
        origin = collection["origin"]
        lines.append(
            f"| `{folder}` | {len(files):,} | {known:,} of {2 * len(files):,} "
            f"| [{origin['short']}]({origin['url']}) | {collection['description']} |"
        )
        cases += len(files)
        labelled += known
    lines.append(f"| All | {cases:,} | {labelled:,} of {2 * cases:,} | | |")
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m subsumes_benchmark.table <corpus>")
    print(collections_table(Path(sys.argv[1])))


if __name__ == "__main__":
    main()
