"""Writes the parts of README.md that are written from data.

    uv run scripts/readme.py            # write them
    uv run scripts/readme.py --check    # fail where the README is not what they give

It is run from the root of the repository, and reads the corpus under ``corpus/`` and the
latest comparison under ``comparison/``. A part lies between the two markers
``<!-- <part>:start -->`` and ``<!-- <part>:end -->``, and the rest of the README stays as it
is. The corpus decides three parts:

- ``collections``: the list of the collections.
- ``num_collections``: how many collections there are.
- ``num_labelled_tasks``: how many tasks have a label.

The comparison decides two:

- ``comparison``: the table of the checkers, which ``subsumes-benchmark report`` wrote as
  ``comparison/results.md``.
- ``version``: the version of the corpus that the checkers ran on, from
  ``comparison/comparison.json``.

Where the first marker ends its line, the part is a block, such as a table: it is set off
from both markers by an empty line. Elsewhere the part stands within a sentence, such as a
number: it follows the first marker directly and has to be one line.

The script fails, and changes nothing, when a part is empty, when the README does not have
each of the two markers of a part exactly once, the first before the second, and when more
than one line is to go within a sentence.

It uses the standard library only, so it runs without the project around it.
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

README = Path("README.md")
CORPUS = Path("corpus")
COMPARISON = Path("comparison")

# The README is the page of the package on PyPI too, so a link in it is a full URL.
REPOSITORY = "https://github.com/georg-wolflein/subsumes-benchmark"


@dataclass(frozen=True)
class Collection:
    """What the README says about one collection of the corpus."""

    folder: str
    description: str
    # The work that first published the pairs, as a short name and where to read it.
    origin: str
    origin_url: str
    cases: int
    # How many of its tasks have a label. A case is two tasks, one for each direction.
    labelled: int


def read_collections(corpus: Path) -> list[Collection]:
    """The collections of a corpus, in the order of its ``manifest.json``."""
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    collections = []
    for folder, collection in manifest["collections"].items():
        files = sorted((corpus / folder).glob("*.json"))
        labelled = 0
        for file in files:
            case = json.loads(file.read_text(encoding="utf-8"))
            labels = case["labels"]
            labelled += (labels["a_subsumes_b"] is not None) + (labels["b_subsumes_a"] is not None)
        collections.append(
            Collection(
                folder=folder,
                description=collection["description"],
                origin=collection["origin"]["short"],
                origin_url=collection["origin"]["url"],
                cases=len(files),
                labelled=labelled,
            )
        )
    return collections


def collections_list(collections: list[Collection]) -> str:
    """The list of the collections: each as a link to its folder, and a line with the sums."""
    items = [
        f"- **[`{c.folder}`]({REPOSITORY}/tree/main/corpus/{c.folder})**: {c.description} "
        f"From [{c.origin}]({c.origin_url}). "
        f"{c.cases:,} cases, {c.labelled:,} of {2 * c.cases:,} tasks with a label."
        for c in collections
    ]
    cases = sum(c.cases for c in collections)
    labelled = sum(c.labelled for c in collections)
    total = f"In all: {cases:,} cases, {labelled:,} of {2 * cases:,} tasks with a label."
    return "\n".join([*items, "", total])


def measured_version(comparison: Path) -> str:
    """The version of the corpus that the checkers ran on, as a link to its release.

    A corpus that is no release, as in a checkout between two of them, has no page to link
    to, so its version stands alone.
    """
    corpus = json.loads((comparison / "comparison.json").read_text(encoding="utf-8"))["corpus"]
    if re.fullmatch(r"v\d+\.\d+\.\d+", corpus):
        return f"[`{corpus}`]({REPOSITORY}/releases/tag/{corpus})"
    return f"`{corpus}`"


def with_part(text: str, part: str, content: str) -> str:
    """The text of the README with one part replaced."""
    content = content.strip("\n")
    if not content:
        sys.exit(f"there is nothing to put into the part {part}")
    start, end = f"<!-- {part}:start -->", f"<!-- {part}:end -->"
    if text.count(start) != 1 or text.count(end) != 1 or text.index(end) < text.index(start):
        sys.exit(f"{README} does not have '{start}' and '{end}' once each, in that order")
    before, rest = text.split(start)
    old, after = rest.split(end)
    if old.startswith("\n"):
        content = f"\n\n{content}\n\n"
    elif "\n" in content:
        sys.exit(f"the part {part} stands within a sentence, and more than one line is given")
    return f"{before}{start}{content}{end}{after}"


def main() -> None:
    if sys.argv[1:] not in ([], ["--check"]):
        sys.exit("usage: readme.py [--check]")
    collections = read_collections(CORPUS)
    parts = {
        "collections": collections_list(collections),
        "num_collections": f"{len(collections):,}",
        "num_labelled_tasks": f"{sum(c.labelled for c in collections):,}",
        "comparison": (COMPARISON / "results.md").read_text(encoding="utf-8"),
        "version": measured_version(COMPARISON),
    }
    written = README.read_text(encoding="utf-8")
    text = written
    stale = []
    for part, content in parts.items():
        replaced = with_part(text, part, content)
        if replaced != text:
            stale.append(part)
        text = replaced
    if sys.argv[1:] == ["--check"]:
        if stale:
            sys.exit(
                f"{README} is not what corpus/ and comparison/ give, in the parts "
                f"{', '.join(stale)}; `make readme` writes them"
            )
    elif stale:
        README.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
