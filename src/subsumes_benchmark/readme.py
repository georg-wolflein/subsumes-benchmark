"""The parts of a README that are written from data, each between two marker lines.

A part has a name, and its markers are the two comments ``<!-- name:start -->`` and
``<!-- name:end -->``, each on a line of its own. What lies between them is replaced as a
whole, and everything else of the file is left as it is.
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from pathlib import Path

type Part = Literal["collections", "comparison"]
"""A part of the README that is written from data.

- ``collections``: the table of the collections, which the build writes from the corpus.
- ``comparison``: the table of the checkers with their results. A report writes it as a file,
  and the ``Comparison`` workflow puts that file here.
"""


class ReadmeError(Exception):
    pass


def markers(part: Part) -> tuple[str, str]:
    """The two lines that a part lies between."""
    return f"<!-- {part}:start -->", f"<!-- {part}:end -->"


def _split(text: str, part: Part, name: str) -> tuple[str, str, str]:
    start, end = markers(part)
    if text.count(start) != 1 or text.count(end) != 1:
        raise ReadmeError(f"{name} does not have the two {part} markers once each")
    before, rest = text.split(start)
    between, after = rest.split(end)
    return before, between, after


def written(text: str, part: Part, block: str) -> str:
    """The text of a README with the block as that part."""
    start, end = markers(part)
    before, _, after = _split(text, part, "the text")
    return f"{before}{start}\n\n{block}\n\n{end}{after}"


def read(readme: Path, part: Part) -> str:
    """What a README has as that part, without the blank lines around it."""
    return _split(readme.read_text(encoding="utf-8"), part, str(readme))[1].strip("\n")


def update(readme: Path, part: Part, block: str) -> None:
    """Replace what lies between the two markers of a part.

    Raises:
        ReadmeError: The file does not have the two markers once each.
    """
    text = readme.read_text(encoding="utf-8")
    _split(text, part, str(readme))
    readme.write_text(written(text, part, block), encoding="utf-8")
