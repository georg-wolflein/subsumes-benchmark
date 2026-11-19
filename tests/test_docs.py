"""The pages say what the corpus has, and their links lead somewhere."""

import re
from typing import TYPE_CHECKING

import pytest

from reading import CORPUS, ROOT
from subsumes_benchmark import readme
from subsumes_benchmark.build import clear, collections_table

if TYPE_CHECKING:
    from pathlib import Path

# The pages that are written by hand, but for the two parts of the first.
PAGES = (
    "README.md",
    "CONTRIBUTING.md",
    "checkers/README.md",
    "corpus/README.md",
    "docs/construction.md",
)
LINK = re.compile(r"\]\(([^)\s]+)\)|(?:src|srcset|href)=\"([^\"]+)\"")


def links(page: str) -> list[str]:
    text = (ROOT / page).read_text(encoding="utf-8")
    return [first or second for first, second in LINK.findall(text)]


def test_the_table_of_the_collections_is_that_of_the_corpus() -> None:
    # `make corpus` writes it; a corpus that was rebuilt without it leaves the table stale.
    assert readme.read(ROOT / "README.md", "collections") == collections_table(CORPUS)


def test_the_readme_links_by_full_urls_only() -> None:
    # It is the page of the package on PyPI too, where a path leads nowhere.
    assert [link for link in links("README.md") if not link.startswith("https://")] == []


def test_the_page_of_the_corpus_leaves_the_corpus_by_full_urls_only() -> None:
    # The page travels in the archive, without the repository around it.
    assert [link for link in links("corpus/README.md") if link.startswith("..")] == []


@pytest.mark.parametrize("page", PAGES)
def test_every_path_that_a_page_links_to_is_there(page: str) -> None:
    folder = (ROOT / page).parent
    missing = [
        link
        for link in links(page)
        if not link.startswith(("https://", "#")) and not (folder / link.split("#")[0]).exists()
    ]
    assert missing == []


@pytest.mark.parametrize("page", PAGES)
def test_every_link_into_this_repository_names_a_file_of_it(page: str) -> None:
    # A full URL to a file on `main` is checked like a path, so that a page that moves is noticed.
    repository = "https://github.com/georg-wolflein/subsumes-benchmark/"
    raw = "https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/"
    missing = []
    for link in links(page):
        for prefix in (f"{repository}blob/main/", f"{repository}tree/main/", raw):
            if (
                link.startswith(prefix)
                and not (ROOT / link.removeprefix(prefix).split("#")[0]).exists()
            ):
                missing.append(link)
    assert missing == []


def test_a_build_leaves_the_page_of_the_corpus_as_it_is(tmp_path: Path) -> None:
    (tmp_path / "origin" / "collection").mkdir(parents=True)
    (tmp_path / "origin" / "collection" / "case.json").write_text("{}", encoding="utf-8")
    (tmp_path / "collections.json").write_text("{}", encoding="utf-8")
    (tmp_path / "README.md").write_text("by hand", encoding="utf-8")
    clear(tmp_path)
    assert [path.name for path in tmp_path.iterdir()] == ["README.md"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "by hand"
    # A folder that is not there yet is none to clear.
    clear(tmp_path / "new")
