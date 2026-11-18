"""The corpus as one file: ``corpus.tar.zst``, which a release and the package carry.

The file is the folder ``corpus/`` as a tar archive compressed with Zstandard. A release of
the repository has it as its file, and the package has the same file next to this module,
from where ``subsumes-benchmark corpus <folder>`` unpacks it. It is not committed: the release
packs it from the corpus of the tag, before the package is built.

``python -m subsumes_benchmark.archive <corpus> <archive>`` packs a corpus; ``make archive``
does so for a build of the package from a checkout.
"""

import sys
import tarfile
from pathlib import Path

# Where the package holds the corpus. In a checkout the file is there only after it was packed.
ARCHIVE = Path(__file__).with_name("corpus.tar.zst")
# The folder that the archive unpacks into, as `tar` unpacks it.
ROOT = "corpus"
# The strongest level that needs no more memory to unpack than a lower one.
LEVEL = 19


class ArchiveError(Exception):
    pass


def pack(corpus: Path, archive: Path) -> None:
    """Pack the folder of a corpus into an archive that depends on nothing but the corpus.

    The entries are sorted, and have no time and no owner, so that the same corpus gives the
    same file wherever it is packed.
    """
    if not corpus.is_dir():
        raise ArchiveError(f"there is no corpus at {corpus}")
    paths = sorted(corpus.rglob("*"), key=lambda path: path.relative_to(corpus).parts)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.TarFile.zstopen(archive, "w", level=LEVEL) as tar:
        for path in [corpus, *paths]:
            name = (Path(ROOT) / path.relative_to(corpus)).as_posix()
            entry = tarfile.TarInfo(name)
            if path.is_dir():
                entry.type, entry.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(entry)
            else:
                entry.size, entry.mode = path.stat().st_size, 0o644
                with path.open("rb") as content:
                    tar.addfile(entry, content)


def unpack(folder: Path, archive: Path = ARCHIVE) -> None:
    """Unpack the corpus of an archive into a folder, which is new or empty.

    The folder becomes the corpus itself: what the archive has under ``corpus/`` goes
    directly into it.

    Raises:
        ArchiveError: There is no archive, or the folder holds something already.
    """
    if not archive.is_file():
        raise ArchiveError(
            f"there is no archive at {archive}: a checkout has the corpus as the folder corpus/, "
            "and only a built package holds the archive"
        )
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise ArchiveError(f"{folder} is not empty")
    folder.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:zst") as tar:
        for entry in tar:
            inside = Path(entry.name).relative_to(ROOT)
            if inside.parts:
                tar.extract(entry.replace(name=inside.as_posix()), folder, filter="data")


if __name__ == "__main__":
    try:
        pack(Path(sys.argv[1]), Path(sys.argv[2]))
    except ArchiveError as error:
        sys.exit(str(error))
