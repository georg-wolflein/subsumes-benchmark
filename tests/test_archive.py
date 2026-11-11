"""The release archive: what it holds, and that it depends on nothing but the files."""

import os
import tarfile
from typing import TYPE_CHECKING

from subsumes_benchmark.archive import archive

if TYPE_CHECKING:
    from pathlib import Path


def write_corpus(root: Path) -> Path:
    corpus = root / "corpus"
    (corpus / "collection" / "case").mkdir(parents=True)
    (corpus / "resources.json").write_text("{}\n", encoding="utf-8")
    (corpus / "collection" / "case" / "b.json").write_text("false\n", encoding="utf-8")
    (corpus / "collection" / "case" / "a.json").write_text("true\n", encoding="utf-8")
    return corpus


def test_archive_holds_every_file_in_order_under_the_name_of_the_corpus(tmp_path: Path) -> None:
    out = tmp_path / "out" / "corpus.tar.zst"
    archive(write_corpus(tmp_path), out)
    with tarfile.open(out, "r:zst") as tar:
        contents = {member.name: tar.extractfile(member) for member in tar.getmembers()}
        assert list(contents) == [
            "corpus/collection/case/a.json",
            "corpus/collection/case/b.json",
            "corpus/resources.json",
        ]
        file = contents["corpus/collection/case/a.json"]
        assert file is not None
        assert file.read() == b"true\n"


def test_archive_depends_on_nothing_but_names_and_contents(tmp_path: Path) -> None:
    corpus = write_corpus(tmp_path)
    first, second = tmp_path / "first.tar.zst", tmp_path / "second.tar.zst"
    archive(corpus, first)
    path = corpus / "resources.json"
    os.utime(path, (1_000_000_000, 1_000_000_000))
    path.chmod(0o600)
    archive(corpus, second)
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:zst") as tar:
        metadata = {(m.mtime, m.uid, m.gid, m.uname, m.gname, m.mode) for m in tar.getmembers()}
    assert metadata == {(0, 0, 0, "", "", 0o644)}
