"""The pages say what the corpus has, and their links lead somewhere."""

import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from reading import CORPUS, ROOT
from subsumes_benchmark.build import clear
from subsumes_benchmark.table import collections_table

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
# The script that puts a part into the README.
SCRIPT = ROOT / "scripts" / "readme-part.sh"


def links(page: str) -> list[str]:
    text = (ROOT / page).read_text(encoding="utf-8")
    return [first or second for first, second in LINK.findall(text)]


def part(name: str) -> str:
    """What the README has between the two marker lines of a part."""
    lines = (ROOT / "README.md").read_text(encoding="utf-8").split("\n")
    start, end = lines.index(f"<!-- {name}:start -->"), lines.index(f"<!-- {name}:end -->")
    return "\n".join(lines[start + 1 : end]).strip("\n")


def put(folder: Path, *arguments: str, text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [SCRIPT, *arguments], cwd=folder, input=text, capture_output=True, text=True, check=False
    )


def test_the_table_of_the_collections_is_that_of_the_corpus() -> None:
    # `make corpus` puts it there; a corpus that was rebuilt without it leaves the table stale.
    assert part("collections") == collections_table(CORPUS)


def test_the_command_prints_the_table_of_the_collections() -> None:
    command = [sys.executable, "-m", "subsumes_benchmark.table", str(CORPUS)]
    printed = subprocess.run(command, capture_output=True, text=True, check=True).stdout
    assert printed == f"{collections_table(CORPUS)}\n"


def test_the_table_of_the_checkers_is_that_of_the_report() -> None:
    # The `Comparison` workflow puts the file of the report into the README.
    table = (ROOT / "comparison" / "results.md").read_text(encoding="utf-8")
    assert part("comparison") == table.strip("\n")


def test_the_script_puts_a_file_between_the_markers_of_a_part(tmp_path: Path) -> None:
    page = tmp_path / "README.md"
    other = "<!-- other:start -->\nkept\n<!-- other:end -->"
    before = f"before\n<!-- one:start -->\n\nold\nolder\n\n<!-- one:end -->\n{other}\nafter\n"
    page.write_text(before, encoding="utf-8")
    # Nothing in a table is read as anything but text.
    table = "| a | 50% of \\n & $HOME |\n\nMeasured on `v1`."
    (tmp_path / "table.md").write_text(f"{table}\n", encoding="utf-8")
    after = f"before\n<!-- one:start -->\n\n{table}\n\n<!-- one:end -->\n{other}\nafter\n"

    assert put(tmp_path, "one", "table.md").returncode == 0
    assert page.read_text(encoding="utf-8") == after
    # A second time changes nothing, and neither does the table on the standard input.
    assert put(tmp_path, "one", "table.md").returncode == 0
    assert put(tmp_path, "one", text=f"{table}\n").returncode == 0
    assert page.read_text(encoding="utf-8") == after


@pytest.mark.parametrize(
    ("readme", "table", "message"),
    [
        ("nothing to replace\n", "a table\n", "exactly once"),
        ("<!-- one:start -->\n<!-- one:start -->\n<!-- one:end -->\n", "a table\n", "exactly once"),
        ("<!-- one:start -->\nold\n<!-- one:end -->\n", "", "nothing to put"),
    ],
)
def test_the_script_fails_and_changes_nothing(
    tmp_path: Path, readme: str, table: str, message: str
) -> None:
    page = tmp_path / "README.md"
    page.write_text(readme, encoding="utf-8")
    done = put(tmp_path, "one", text=table)
    assert done.returncode != 0
    assert message in done.stderr
    assert page.read_text(encoding="utf-8") == readme


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
