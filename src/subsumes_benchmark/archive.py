"""Pack ``corpus/`` into the archive that a release carries.

The archive is a tar file compressed with Zstandard. Its bytes depend on nothing but the names
and contents of the files: the entries are sorted, and each has the same owner, mode and time.
Run from the repository root::

    make archive
"""

import argparse
import hashlib
import tarfile
from compression.zstd import CompressionParameter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

# Level 19 packs the corpus into about 4 MB; higher levels gain little and take far longer.
OPTIONS: Mapping[int, int] = {CompressionParameter.compression_level: 19}


def archive(corpus: Path, out: Path) -> None:
    """Write every file below ``corpus`` to ``out``, under paths that start with its name."""
    names = sorted(
        path.relative_to(corpus.parent).as_posix() for path in corpus.rglob("*") if path.is_file()
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:zst", options=OPTIONS) as tar:
        for name in names:
            path = corpus.parent / name
            # A bare TarInfo has no owner, time 0 and mode 644, whatever the file has on disk.
            entry = tarfile.TarInfo(name)
            entry.size = path.stat().st_size
            with path.open("rb") as file:
                tar.addfile(entry, file)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pack the corpus into a release archive.")
    parser.add_argument("--corpus", type=Path, default=Path("corpus"), help="what to pack")
    parser.add_argument("--out", type=Path, default=Path("dist/corpus.tar.zst"))
    args = parser.parse_args()
    archive(args.corpus, args.out)
    data = args.out.read_bytes()
    print(f"{args.out}: {len(data) / 1e6:.1f} MB, sha256 {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
