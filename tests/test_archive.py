"""The corpus as one archive: packing it, and unpacking it as the installed package does."""

import subprocess
import sys
import tarfile
from typing import TYPE_CHECKING

import pytest

from subsumes_benchmark.archive import ARCHIVE, ArchiveError, pack, unpack

if TYPE_CHECKING:
    from pathlib import Path

FILES = {
    "case.schema.json": "{}",
    "licenses/one.txt": "a licence",
    "strings/collection.json": '{"description": "strings"}',
    "strings/group/a.json": '{"a": true, "b": "é"}',
    "strings/group.b.json": '{"a": true, "b": false}',
}


def a_corpus(folder: Path) -> Path:
    for name, content in FILES.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return folder


def files(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): path.read_text(encoding="utf-8")
        for path in folder.rglob("*")
        if path.is_file()
    }


def test_a_corpus_that_is_packed_and_unpacked_is_the_same(tmp_path: Path) -> None:
    archive = tmp_path / "corpus.tar.zst"
    pack(a_corpus(tmp_path / "corpus"), archive)
    # Into a folder that is not there yet, and into one that is there and empty.
    (tmp_path / "empty").mkdir()
    for folder in (tmp_path / "new" / "corpus", tmp_path / "empty"):
        unpack(folder, archive)
        assert files(folder) == FILES


def test_the_archive_depends_on_nothing_but_the_corpus(tmp_path: Path) -> None:
    first, second = tmp_path / "first.tar.zst", tmp_path / "second.tar.zst"
    pack(a_corpus(tmp_path / "one" / "corpus"), first)
    pack(a_corpus(tmp_path / "another" / "place"), second)
    assert first.read_bytes() == second.read_bytes()
    # Whatever the folder was called, the archive unpacks into `corpus/`, as `tar` unpacks it,
    # with its entries sorted folder by folder and without a time or an owner.
    with tarfile.open(first, "r:zst") as tar:
        entries = tar.getmembers()
    assert [entry.name for entry in entries] == [
        "corpus",
        "corpus/case.schema.json",
        "corpus/licenses",
        "corpus/licenses/one.txt",
        "corpus/strings",
        "corpus/strings/collection.json",
        "corpus/strings/group",
        "corpus/strings/group/a.json",
        "corpus/strings/group.b.json",
    ]
    assert {(entry.mtime, entry.uid, entry.gid, entry.uname) for entry in entries} == {
        (0, 0, 0, "")
    }


def test_nothing_is_unpacked_over_what_is_there(tmp_path: Path) -> None:
    archive = tmp_path / "corpus.tar.zst"
    pack(a_corpus(tmp_path / "corpus"), archive)
    taken = tmp_path / "taken"
    taken.mkdir()
    (taken / "mine.txt").write_text("kept", encoding="utf-8")
    with pytest.raises(ArchiveError, match="is not empty"):
        unpack(taken, archive)
    assert files(taken) == {"mine.txt": "kept"}
    with pytest.raises(ArchiveError, match="is not empty"):
        unpack(taken / "mine.txt", archive)


def test_without_an_archive_the_command_says_where_the_corpus_is(tmp_path: Path) -> None:
    with pytest.raises(ArchiveError, match="there is no archive"):
        unpack(tmp_path / "corpus", tmp_path / "none.tar.zst")
    with pytest.raises(ArchiveError, match="there is no corpus"):
        pack(tmp_path / "none", tmp_path / "corpus.tar.zst")
    # The command unpacks the archive of the package, which a checkout has only once it was
    # packed. Either way it ends without a traceback.
    command = [sys.executable, "-m", "subsumes_benchmark.compare", "corpus", str(tmp_path / "out")]
    done = subprocess.run(command, check=False, capture_output=True, text=True)
    if ARCHIVE.is_file():
        assert done.returncode == 0
        assert (tmp_path / "out" / "case.schema.json").is_file()
    else:
        assert done.returncode == 1
        assert done.stderr.startswith("there is no archive at ")
