"""Build ``corpus/`` from the upstream sources checked out under ``sources/``.

Two sources are read at the commits their submodules pin:

1. The official JSON Schema Test Suite: schemas with instances that are valid under them or
   not. From its test cases for draft 2020-12 the build constructs pairs of schemas whose
   inclusion is known (``testsuite``).
2. The inclusion artifact of "JSON Schema Inclusion through Refutational Normalization"
   (2026): seven datasets of fused tests in older drafts, which are split back into their two
   schemas (``unfuse``) and converted to draft 2020-12 (``convert``).

Every case becomes one file ``corpus/<origin>/<collection>/<name>.json`` holding the labels, what
the two schemas use (``features``) and the two schemas, ``a`` and ``b``. The question a case
asks is always whether ``a`` accepts every instance valid under ``b``. The artifact lists the
narrower schema first, so ``b`` is its first schema and ``a`` its second. A schema that
references other documents carries them embedded (``bundled``), so every schema stands on its
own.

The origin is the work that first published the pairs of a collection, by its citation key,
and not the source that the build reads them from. ``collections.json`` names the
collections, the origin of each and the source it is read from; ``overrides.json``
lists the cases that are left out and the cases whose label departs from upstream's;
``derived.json`` holds the labels of questions that upstream leaves open, each with what
shows it. Run from the repository root::

    make sources   # once: check out the upstream submodules
    make corpus
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Self, assert_never
from urllib.parse import quote, urldefrag, urljoin

from pydantic import model_validator

from subsumes_benchmark import Json
from subsumes_benchmark.config import ConfigError
from subsumes_benchmark.convert import (
    ConversionError,
    Converter,
    PointerMap,
    dialect_of,
    nested,
)
from subsumes_benchmark.derived import Derivations, by_label, document, label
from subsumes_benchmark.features import features
from subsumes_benchmark.generated.collections import (
    CollectionSpec,
    CollectionsSpec,
    OriginSpec,
    SourceSpec,
)
from subsumes_benchmark.generated.derived import Derived
from subsumes_benchmark.generated.overrides import Override, OverridesSpec
from subsumes_benchmark.testsuite import SuiteCase, pairs
from subsumes_benchmark.unfuse import unfuse

SOURCES = Path("sources")

# The directory of a fused test is the artifact's answer to "is S1 included in S2?".
VERDICT_DIRS: Mapping[str, bool | None] = {"sat": False, "unsat": True, "unknown": None}

# The schema of a case, written by hand. The corpus carries a copy of it.
CASE_SCHEMA = Path("schemas/case.schema.json")

# What the corpus says about its collections, by the folder of each, in one file at its root.
MANIFEST_NAME = "collections.json"

# The page of the corpus, which is written by hand and which a build leaves as it is.
README_NAME = "README.md"

# The licence of a collection, which is that of its source, in the folder of the collection.
LICENSE_NAME = "LICENSE"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


class Collections(CollectionsSpec):
    """``collections.json``, with what its schema cannot say."""

    @model_validator(mode="after")
    def _every_source_is_listed(self) -> Self:
        named = {collection.source for collection in self.collections.values()}
        if unknown := sorted(named - self.sources.keys()):
            raise ValueError(f"collections are built from sources that are not listed: {unknown}")
        return self

    @model_validator(mode="after")
    def _the_origins_are_those_of_the_collections(self) -> Self:
        named = {collection.origin for collection in self.collections.values()}
        if unknown := sorted(named - self.origins.keys()):
            raise ValueError(f"collections have origins that are not listed: {unknown}")
        if unused := sorted(self.origins.keys() - named):
            raise ValueError(f"origins without a collection: {unused}")
        return self


@dataclass(frozen=True)
class Source:
    """An upstream repository, checked out as a submodule under ``sources/``."""

    name: str
    spec: SourceSpec
    root: Path
    repository: str
    commit: str

    @classmethod
    def create(cls, name: str, spec: SourceSpec) -> Self:
        root = SOURCES / name
        if not (root / spec.license_file).exists():
            raise ConfigError(f"{root} is not checked out; run `make sources`")
        return cls(
            name=name,
            spec=spec,
            root=root,
            repository=git("config", "-f", ".gitmodules", "--get", f"submodule.{root}.url"),
            commit=git("-C", str(root), "rev-parse", "HEAD"),
        )

    @property
    def license_file(self) -> Path:
        return self.root / self.spec.license_file

    def permalink(self, path: Path) -> str:
        """The address of a file of this source at the commit the corpus is built from."""
        match self.spec.forge:
            case "github":
                blob = "blob"
            case "gitlab":
                blob = "-/blob"
            case _:
                assert_never(self.spec.forge)
        file = quote(path.relative_to(self.root).as_posix())
        return f"{self.repository.removesuffix('.git')}/{blob}/{self.commit}/{file}"


@dataclass(frozen=True)
class Collection:
    """A named part of the corpus, built from one dataset of one source."""

    name: str
    source: Source
    origin: OriginSpec
    spec: CollectionSpec

    @property
    def folder(self) -> str:
        """The folder of the collection below ``corpus/``: what the id of its cases starts with."""
        return f"{self.spec.origin}/{self.name}"

    @property
    def manifest(self) -> Json:
        """What ``corpus/collections.json`` says about the collection."""
        return {
            "description": self.spec.description,
            "use_case": self.spec.use_case,
            "labels": self.spec.labels,
            "origin": {
                "short": self.origin.short,
                "citation": self.origin.citation,
                "url": self.origin.url,
            },
            "license": self.source.spec.license,
            "license_file": f"{self.folder}/{LICENSE_NAME}",
            "source": {
                "repository": self.source.repository,
                "commit": self.source.commit,
                "path": self.spec.path,
            },
        }


class Overrides(OverridesSpec):
    """``overrides.json``, with what its schema cannot say, and its entries by case."""

    @model_validator(mode="after")
    def _a_case_is_listed_once(self) -> Self:
        listed = Counter(case for entry in (*self.exclude, *self.override) for case in entry.cases)
        if repeated := sorted(case for case, count in listed.items() if count > 1):
            raise ValueError(f"listed more than once: {repeated}")
        return self

    @property
    def exclusions(self) -> dict[str, str]:
        """The reason of everything that is left out.

        A key is a case id, or the beginning of a name up to a dot followed by ``.*``, for
        every case of the collection whose name begins so.
        """
        return {case: entry.reason for entry in self.exclude for case in entry.cases}

    @property
    def overrides(self) -> dict[str, Override]:
        """The override of every case that has one, by case id."""
        return {case: entry for entry in self.override for case in entry.cases}


@dataclass(frozen=True)
class Case:
    id: str
    a: Json
    b: Json
    a_subsumes_b: bool | None
    b_subsumes_a: bool | None
    upstream: str
    note: str | None = None
    derived: Derived | None = None
    duplicates: Sequence[str] = ()

    @property
    def document(self) -> Json:
        """What the file of the case holds: what is known first, the two schemas last."""
        out: dict[str, Json] = {
            "$schema": f"../../{CASE_SCHEMA.name}",
            "a_subsumes_b": self.a_subsumes_b,
            "b_subsumes_a": self.b_subsumes_a,
            "features": list(features(self.a, self.b)),
            "upstream": self.upstream,
        }
        if self.duplicates:
            out["duplicates"] = list(self.duplicates)
        if self.note is not None:
            out["note"] = self.note
        if self.derived is not None:
            out["derived"] = document(self.derived)
        return {**out, "a": self.a, "b": self.b}


def load_collections(path: Path) -> list[Collection]:
    config = Collections.read(path)
    sources = {name: Source.create(name, spec) for name, spec in config.sources.items()}
    return [
        Collection(name, sources[spec.source], config.origins[spec.origin], spec)
        for name, spec in config.collections.items()
    ]


# --------------------------------------------------------------------------- the inclusion artifact


def external_refs(node: Json, base: str, out: set[str]) -> None:
    """Collect absolute URLs (without fragment) of every non-local reference."""
    if isinstance(node, list):
        for item in node:
            external_refs(item, base, out)
    elif isinstance(node, dict):
        for key in ("id", "$id"):
            value = node.get(key)
            if isinstance(value, str) and not value.startswith("#"):
                base = urljoin(base, value) if base else value
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            out.add(urldefrag(urljoin(base, ref) if base else ref)[0])
        for value in nested(node):
            external_refs(value, base, out)


def read_external_documents(
    source: Source, collections: Sequence[Collection]
) -> tuple[dict[str, Json], dict[str, PointerMap]]:
    """The documents the artifact's tests reference, transitively, converted to draft 2020-12.

    They come from the artifact's cache, which names each file by the SHA-256 of its URL. The
    pointer maps say where each node of a document moved, for the references into it.
    """
    cache: dict[str, Path] = {}
    for path in (source.root / ".schema-cache").iterdir():
        if match := re.search(r"([0-9a-f]{64})\.json$", path.name):
            cache[match.group(1)] = path
    needed: set[str] = set()
    for collection in collections:
        for path in (source.root / collection.spec.path).rglob("*.json"):
            external_refs(json.loads(path.read_text(encoding="utf-8")), "", needed)
    converted: dict[str, tuple[Converter, Json]] = {}
    pending = sorted(needed)
    while pending:
        url = pending.pop()
        if url in converted:
            continue
        digest = hashlib.sha256(url.encode()).hexdigest()
        if digest not in cache:
            raise ConversionError(f"external reference {url} is not in the artifact's cache")
        raw = json.loads(cache[digest].read_text(encoding="utf-8"))
        more: set[str] = set()
        external_refs(raw, url, more)
        pending.extend(sorted(more - set(converted)))
        converter = Converter()
        schema = converter.convert(raw, base=url)
        if isinstance(schema, dict):
            schema["$id"] = url
        converted[url] = (converter, schema)
    pointer_maps = {url: converter.pmap for url, (converter, _) in converted.items()}
    documents = {
        url: converter.rewrite_refs(schema, pointer_maps)
        for url, (converter, schema) in converted.items()
    }
    return documents, pointer_maps


def bundled(schema: Json, documents: Mapping[str, Json]) -> Json:
    """The schema with every document it references embedded, so that it needs nothing else.

    This is the bundling of the specification (JSON Schema Core, section 9.3): a document goes
    under ``$defs`` by its URL and has that URL as its ``$id``, so no reference changes.
    """
    # A reference to the URL of the schema itself, from anywhere, is a reference to the schema.
    own = schema.get("$id") if isinstance(schema, dict) else None
    reached: set[str] = set()
    pending: set[str] = set()
    external_refs(schema, "", pending)
    while pending:
        url = pending.pop()
        if url in reached or url == own or url not in documents:
            continue
        reached.add(url)
        external_refs(documents[url], url, pending)
    if not reached:
        return schema
    assert isinstance(schema, dict)
    definitions = schema.get("$defs", {})
    assert isinstance(definitions, dict)
    embedded: dict[str, Json] = {}
    for url in sorted(reached):
        document = documents[url]
        if not isinstance(document, dict) or document.get("$id") != url:
            raise ConversionError(f"{url} does not identify itself, so it cannot be embedded")
        if url in definitions:
            raise ConversionError(f"{url} is in the schema already")
        embedded[url] = document
    return schema | {"$defs": definitions | embedded}


def read_inclusion(
    collection: Collection,
    pointer_maps: dict[str, PointerMap],
    notes: Counter[str],
    dialects: Counter[str],
) -> Iterator[Case]:
    dataset = collection.source.root / collection.spec.path
    for verdict_dir, included in VERDICT_DIRS.items():
        for path in sorted((dataset / verdict_dir).glob("*.json")):
            try:
                s1, s2, applied = unfuse(json.loads(path.read_text(encoding="utf-8")))
                sides: list[Json] = []
                for raw in (s1, s2):
                    dialects[dialect_of(raw)] += 1
                    converter = Converter()
                    sides.append(converter.rewrite_refs(converter.convert(raw), pointer_maps))
                    applied |= converter.notes
            except ConversionError as exc:
                raise ConversionError(f"{path}: {exc}") from exc
            notes.update(applied)
            yield Case(
                id=f"{collection.folder}/{path.stem}",
                a=sides[1],
                b=sides[0],
                a_subsumes_b=included,
                b_subsumes_a=None,
                upstream=collection.source.permalink(path),
            )


# --------------------------------------------------------------------------- the test suite


def external_schemas(given: Mapping[str, Json]) -> dict[str, Json]:
    """The schemas a test case of the suite makes available, each identifying itself by its URL.

    The suite leaves ``$id`` out of them where it can and gives the URL as the key instead. A
    schema that gives itself another ``$id`` than the URL it is fetched from is left out: an
    embedded schema is known by its ``$id`` only, so a reference to that URL cannot resolve in
    a schema that stands on its own, and ``overrides.json`` excludes the test case.
    """
    documents: dict[str, Json] = {}
    for url, schema in given.items():
        if not isinstance(schema, dict):
            raise ConversionError(f"external schema {url} is no object and cannot carry an $id")
        if schema.get("$id", url) == url:
            documents[url] = {"$id": url} | schema
    return documents


def as_doubles(node: object, lost: set[str]) -> Json:
    """A JSON value read with ``Decimal`` numbers, with those numbers as floats.

    ``lost`` collects the numerals that a double does not hold exactly as they are written.
    """
    if isinstance(node, Decimal):
        if Decimal(repr(float(node))) != node:
            lost.add(str(node))
        return float(node)
    if isinstance(node, list):
        return [as_doubles(item, lost) for item in node]
    if isinstance(node, dict):
        return {key: as_doubles(value, lost) for key, value in node.items()}
    assert node is None or isinstance(node, bool | int | str)
    return node


def read_test_suite(collection: Collection, exclusions: Mapping[str, str]) -> Iterator[Case]:
    """The pairs built from every test case of the suite that holds for draft 2020-12.

    A test case is left out when it is for other releases of the specification, when it
    belongs to a proposal, or when it expects ``format`` to be an annotation. The corpus
    writes numbers as doubles, so a test case with a number that a double does not hold
    must be one that ``overrides.json`` excludes.
    """
    tests_dir = collection.source.root / collection.spec.path
    for path in sorted(tests_dir.rglob("*.json")):
        file = path.relative_to(tests_dir).with_suffix("")
        if file.parts[0] == "proposals":
            continue
        if any("." in part for part in file.parts):
            raise ConversionError(
                f"{path}: a dot in the name would read as a part of a case's name"
            )
        name = ".".join(file.parts)
        document = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        for index, exact in enumerate(document["tests"]):
            lost: set[str] = set()
            test_case = SuiteCase.create(as_doubles(exact, lost))
            if not test_case.holds_for_the_corpus:
                continue
            upstream = f"{collection.source.permalink(path)}#/tests/{index}"
            test_case_name = f"{collection.folder}/{name}.{index}"
            if lost and exclusion_of(f"{test_case_name}.reflexive", exclusions) is None:
                raise ConversionError(f"{upstream}: a double does not hold {sorted(lost)}")
            try:
                schema = bundled(test_case.schema, external_schemas(test_case.external_schemas))
                built = list(pairs(schema, test_case.instances))
            except ConversionError as exc:
                raise ConversionError(f"{upstream}: {exc}") from exc
            for pair in built:
                of_test = pair.test is not None
                yield Case(
                    id=f"{test_case_name}.{pair.category}" + (f".{pair.test}" if of_test else ""),
                    a=pair.a,
                    b=pair.b,
                    a_subsumes_b=pair.a_subsumes_b,
                    b_subsumes_a=pair.b_subsumes_a,
                    upstream=upstream + (f"/tests/{pair.test}" if of_test else ""),
                )


def _digest(schema: Json) -> bytes:
    """What tells a schema from every other one: two that are the same JSON value have the same."""
    return hashlib.sha256(json.dumps(schema, sort_keys=True).encode()).digest()


def _one(case: Case, name: str, answers: Sequence[tuple[Case, bool | None]]) -> bool | None:
    """The one answer that cases give to a question of ``case``, or ``None`` if none gives one."""
    given = {answer: other for other, answer in answers if answer is not None}
    if len(given) > 1:
        raise ConversionError(
            f"{given[True].id} and {given[False].id} hold the same two schemas and give "
            f"{name} of {case.id} two answers"
        )
    return next(iter(given), None)


def without_duplicates(cases: Sequence[Case]) -> list[Case]:
    """One case for every pair of schemas, with what every case of that pair says.

    Two cases are duplicates when they hold the same two schemas, in either order. Upstream
    asks many a question twice: the suite tests some schemas with the same instance twice,
    and the artifact asks most of its questions in both directions, as two tests. Of such
    cases the one whose id sorts first is kept. It answers each direction with what any of
    them says about it, has their notes, and lists the upstream files of the others.

    A case whose two schemas are the same is a duplicate only of the cases with that schema.
    Its two directions are one question, and still each keeps the label it has.

    Raises:
        ConversionError: Two duplicates give one question two answers.
    """
    digests = {case.id: (_digest(case.a), _digest(case.b)) for case in cases}
    groups: dict[frozenset[bytes], list[Case]] = {}
    for case in cases:
        groups.setdefault(frozenset(digests[case.id]), []).append(case)
    kept: dict[str, Case] = {}
    for group in groups.values():
        first, *others = sorted(group, key=lambda case: case.id.split("/"))
        if not others:
            kept[first.id] = first
            continue
        forward, backward = [(first, first.a_subsumes_b)], [(first, first.b_subsumes_a)]
        for other in others:
            mirrored = digests[other.id] != digests[first.id]
            forward.append((other, other.b_subsumes_a if mirrored else other.a_subsumes_b))
            backward.append((other, other.a_subsumes_b if mirrored else other.b_subsumes_a))
        notes = dict.fromkeys(case.note for case in group if case.note is not None)
        links = dict.fromkeys(
            other.upstream for other in others if other.upstream != first.upstream
        )
        kept[first.id] = replace(
            first,
            a_subsumes_b=_one(first, "a_subsumes_b", forward),
            b_subsumes_a=_one(first, "b_subsumes_a", backward),
            note=" ".join(notes) or None,
            duplicates=tuple(links),
        )
    return [kept[case.id] for case in cases if case.id in kept]


# --------------------------------------------------------------------------- writing


def write_json(path: Path, data: Json) -> None:
    """Write indented JSON, with every non-ASCII character escaped so that none is invisible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_case(out: Path, case: Case) -> None:
    write_json(out / f"{case.id}.json", case.document)


def exclusion_of(case_id: str, exclusions: Mapping[str, str]) -> str | None:
    """The entry of ``overrides.json`` that leaves the case out: its id, or how its name begins.

    Such a beginning ends at a dot of the name and is followed by ``.*``, so
    ``.../minimum.3.*`` leaves out every pair built from one test case of the suite.
    """
    if case_id in exclusions:
        return case_id
    collection, _, name = case_id.rpartition("/")
    parts = name.split(".")
    for length in range(len(parts) - 1, 0, -1):
        if (beginning := f"{collection}/{'.'.join(parts[:length])}.*") in exclusions:
            return beginning
    return None


def without_excluded(cases: Sequence[Case], exclusions: Mapping[str, str]) -> list[Case]:
    """The cases that ``overrides.json`` does not leave out."""
    kept: list[Case] = []
    used: set[str] = set()
    for case in cases:
        if (entry := exclusion_of(case.id, exclusions)) is None:
            kept.append(case)
        else:
            used.add(entry)
    if missing := sorted(exclusions.keys() - used):
        raise ConfigError(f"overrides.json excludes cases that do not exist: {missing}")
    return kept


def overridden(cases: Sequence[Case], overrides: Mapping[str, Override]) -> list[Case]:
    """The cases with the labels and notes of their overrides."""
    ids = Counter(case.id for case in cases)
    if duplicates := sorted(i for i, n in ids.items() if n > 1):
        raise ConversionError(f"duplicate case ids: {duplicates}")
    if missing := sorted(overrides.keys() - ids.keys()):
        raise ConfigError(f"overrides.json lists cases that do not exist: {missing}")
    return [
        replace(
            case,
            a_subsumes_b=override.a_subsumes_b,
            b_subsumes_a=override.b_subsumes_a,
            note=override.note,
        )
        if (override := overrides.get(case.id))
        else case
        for case in cases
    ]


def with_derived(cases: Sequence[Case], derived: Mapping[str, Derived]) -> list[Case]:
    """The cases with the labels of ``derived.json``.

    Such a label may only stand where a case has none and no override states its labels.
    """
    if missing := sorted(derived.keys() - {case.id for case in cases}):
        raise ConfigError(f"derived.json lists cases that do not exist: {missing}")
    found = []
    for case in cases:
        if (entry := derived.get(case.id)) is None:
            found.append(case)
            continue
        if taken := [name for name, _ in by_label(entry) if getattr(case, name) is not None]:
            raise ConfigError(f"derived.json labels {case.id}, which has a label: {taken}")
        if case.note is not None:
            # An override states both labels of its cases, also where it claims nothing.
            raise ConfigError(f"derived.json labels {case.id}, which overrides.json lists")
        shown = {name: label(evidence) for name, evidence in by_label(entry)}
        found.append(replace(case, derived=entry, **shown))
    return found


def clear(out: Path) -> None:
    """Remove what a build wrote to the folder of the corpus: everything but its ``README.md``.

    That page is the one file of the corpus that is written by hand.
    """
    if not out.exists():
        return
    for path in out.iterdir():
        if path.is_dir():
            shutil.rmtree(path)
        elif path.name != README_NAME:
            path.unlink()


def build(
    out: Path,
    collections_file: Path,
    overrides_file: Path,
    derived_file: Path,
) -> None:
    """Build the corpus."""
    collections = load_collections(collections_file)
    departures = Overrides.read(overrides_file)
    derived = Derivations.read(derived_file).cases
    overrides = departures.overrides
    exclusions = departures.exclusions
    sources = {c.source.name: c.source for c in collections}
    artifact = [c for c in collections if c.source.name == "inclusion-artifact"]

    documents, pointer_maps = read_external_documents(sources["inclusion-artifact"], artifact)

    notes: Counter[str] = Counter()
    dialects: Counter[str] = Counter()
    cases: dict[str, list[Case]] = {}
    for collection in collections:
        print(f"reading {collection.folder}")
        match collection.source.name:
            case "json-schema-test-suite":
                cases[collection.folder] = list(read_test_suite(collection, exclusions))
            case "inclusion-artifact":
                cases[collection.folder] = list(
                    read_inclusion(collection, pointer_maps, notes, dialects)
                )
            case other:
                raise ConfigError(f"no reader for source {other}")
    upstream = [case for group in cases.values() for case in group]
    included = without_excluded(upstream, exclusions)
    selected = overridden(included, overrides)
    whole = [
        replace(case, a=bundled(case.a, documents), b=bundled(case.b, documents))
        for case in selected
    ]
    bundles = sum(
        (after.a is not before.a) + (after.b is not before.b)
        for before, after in zip(selected, whole, strict=True)
    )
    distinct = without_duplicates(whole)
    final = with_derived(distinct, derived)

    # An id is an origin, a collection and a name: no case lies deeper, whatever upstream calls it.
    if deeper := sorted(case.id for case in final if case.id.count("/") != 2):
        raise ConversionError(f"cases that do not lie in the folder of their collection: {deeper}")
    clear(out)
    print(f"writing {len(final)} cases")
    for case in final:
        write_case(out, case)
    write_json(
        out / MANIFEST_NAME, {collection.folder: collection.manifest for collection in collections}
    )
    shutil.copyfile(CASE_SCHEMA, out / CASE_SCHEMA.name)
    for collection in collections:
        collection.source.license_file.copy(out / collection.folder / LICENSE_NAME)

    print(f"\n{'collection':40s} {'cases':>6s} {'true':>6s} {'false':>6s} {'null':>6s}")
    by_id = {case.id: case for case in final}
    for name, group in cases.items():
        kept = [by_id[case.id] for case in group if case.id in by_id]
        labels = Counter(case.a_subsumes_b for case in kept)
        print(f"{name:40s} {len(kept):6d} {labels[True]:6d} {labels[False]:6d} {labels[None]:6d}")
    print(
        f"\n{len(documents)} external documents embedded in the {bundles} schemas that "
        f"reference them, {len(overrides)} overridden cases, {len(upstream) - len(included)} "
        f"excluded cases, {len(included) - len(distinct)} duplicate cases left out, "
        f"{sum(len(list(by_label(entry))) for entry in derived.values())} derived labels"
    )
    print("\nwhat each side of the inclusion artifact declared as its dialect:")
    for dialect, n in dialects.most_common():
        print(f"  {n:6d}  {dialect}")
    print("\nconversions applied, by number of cases:")
    for note, n in notes.most_common():
        print(f"  {n:6d}  {note}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the corpus from the upstream sources.")
    parser.add_argument("--out", type=Path, default=Path("corpus"), help="where to write it")
    parser.add_argument("--collections", type=Path, default=Path("collections.json"))
    parser.add_argument("--overrides", type=Path, default=Path("overrides.json"))
    parser.add_argument("--derived", type=Path, default=Path("derived.json"))
    args = parser.parse_args()
    build(args.out, args.collections, args.overrides, args.derived)
