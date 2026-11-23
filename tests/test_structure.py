"""The committed corpus has the layout the README describes."""

import json
from typing import assert_never

import jsonschema_rs

from reading import CORPUS, ROOT, cases, read
from subsumes_benchmark.build import Overrides, exclusion_of
from subsumes_benchmark.generated.case import CaseSpec
from subsumes_benchmark.generated.manifest import FromGenerator, FromSource, ManifestSpec

CONFIG = json.loads((ROOT / "collections.json").read_text(encoding="utf-8"))
ORIGINS = CONFIG["origins"]
# The collections by their folder below the corpus: the origin and the name.
COLLECTIONS = {f"{spec['origin']}/{name}": spec for name, spec in CONFIG["collections"].items()}
MANIFEST = CORPUS / "manifest.json"


def test_every_file_is_a_case_or_a_shared_file() -> None:
    shared = (
        {CORPUS / "case.schema.json", CORPUS / "manifest.schema.json", MANIFEST}
        | {CORPUS / "README.md"}
        | {CORPUS / folder / "LICENSE" for folder in COLLECTIONS}
        | {case.file for case in cases()}
    )
    stray = [
        path.relative_to(CORPUS).as_posix()
        for path in CORPUS.rglob("*")
        if path.is_file() and path not in shared
    ]
    assert stray == []


def test_every_case_lies_in_the_folder_of_a_collection_of_an_origin() -> None:
    # A folder of the corpus is an origin or a collection of one, and holds nothing deeper.
    folders = {path.relative_to(CORPUS).as_posix() for path in CORPUS.rglob("*") if path.is_dir()}
    assert folders == {*ORIGINS, *COLLECTIONS}
    assert {case.collection for case in cases()} == set(COLLECTIONS)
    assert [case.id for case in cases() if case.id.count("/") != 2] == []


def test_every_case_matches_the_case_schema() -> None:
    # The schema also says that the two schemas of a case are valid draft 2020-12. Over the
    # million and a half schemas of the corpus ``jsonschema-rs`` takes seconds where
    # ``jsonschema`` takes minutes. The metaschema comes with it; offline, it fetches nothing.
    schema = read(ROOT / "schemas" / "case.schema.json")
    assert isinstance(schema, dict)
    validator = jsonschema_rs.Draft202012Validator(schema, offline=True)
    invalid = {}
    for case in cases():
        errors = [
            f"{'/'.join(map(str, error.instance_path))}: {error.message[:160]}"
            for error in validator.iter_errors(read(case.file))
        ]
        if errors:
            invalid[case.id] = errors
    assert invalid == {}


def test_every_case_is_read_by_the_model_of_a_case_and_names_its_schema() -> None:
    # The model generated from the schema takes the two schemas of a case as they are.
    schema = (CORPUS / "case.schema.json").resolve()
    assert schema.read_bytes() == (ROOT / "schemas" / "case.schema.json").read_bytes()
    elsewhere = [
        case.id
        for case in cases()
        if (case.file.parent / CaseSpec.read(case.file).field_schema).resolve() != schema
    ]
    assert elsewhere == []


def test_the_manifest_matches_its_schema_and_names_it() -> None:
    schema = read(ROOT / "schemas" / "manifest.schema.json")
    assert isinstance(schema, dict)
    validator = jsonschema_rs.Draft202012Validator(schema, offline=True, validate_formats=True)
    errors = [
        f"{'/'.join(map(str, error.instance_path))}: {error.message[:160]}"
        for error in validator.iter_errors(read(MANIFEST))
    ]
    assert errors == []
    copy = CORPUS / "manifest.schema.json"
    assert copy.read_bytes() == (ROOT / "schemas" / "manifest.schema.json").read_bytes()
    assert (CORPUS / ManifestSpec.read(MANIFEST).field_schema).resolve() == copy.resolve()


def test_every_upstream_is_a_permalink_into_the_dataset_of_its_collection() -> None:
    blob = {"github": "blob", "gitlab": "-/blob"}
    datasets = {}
    for folder, collection in ManifestSpec.read(MANIFEST).collections.items():
        if isinstance(source := collection.built_from, FromSource):
            forge = CONFIG["sources"][COLLECTIONS[folder]["built_from"]["name"]]["forge"]
            base = source.repository.removesuffix(".git")
            datasets[folder] = f"{base}/{blob[forge]}/{source.commit}/{source.path}/"
    # A case of a generated collection says what it was generated from in place of a link.
    elsewhere = [
        case.id
        for case in cases()
        if (case.upstream is None) != (case.collection not in datasets)
        or (case.upstream is not None and not case.upstream.startswith(datasets[case.collection]))
        or (case.generated is None) != (case.upstream is not None)
    ]
    assert elsewhere == []


def test_the_manifest_says_of_every_collection_what_the_configuration_says() -> None:
    listed = ManifestSpec.read(MANIFEST).collections
    assert list(listed) == list(COLLECTIONS)
    for folder, spec in COLLECTIONS.items():
        collection, built_from = listed[folder], spec["built_from"]
        assert collection.built_from.kind == built_from["kind"]
        match collection.built_from:
            case FromGenerator(path=path):
                # What a generator builds is under the licence of this repository, and the
                # manifest names the file of the generator in it.
                assert (ROOT / path).is_file()
                licence = "MIT"
            case FromSource(path=path):
                assert path == built_from["path"]
                licence = CONFIG["sources"][built_from["name"]]["license"]
            case _:
                assert_never(collection.built_from)
        assert collection.description == spec["description"]
        assert (collection.use_case, collection.labels) == (spec["use_case"], spec["labels"])
        assert collection.origin.model_dump() == ORIGINS[spec["origin"]]
        assert (collection.license, collection.license_file) == (licence, f"{folder}/LICENSE")


def test_every_collection_has_the_license_of_its_source() -> None:
    # A collection folder holds its cases and the licence they are under, and nothing else.
    # Two collections have the same text exactly where they come from the same source, and a
    # generated collection has the text of this repository's licence.
    texts: dict[str, set[bytes]] = {}
    for folder, spec in COLLECTIONS.items():
        text = (CORPUS / folder / "LICENSE").read_bytes()
        built_from = spec["built_from"]
        if built_from["kind"] == "generator":
            assert text == (ROOT / "LICENSE").read_bytes(), folder
            texts.setdefault("this repository", set()).add(text)
        else:
            texts.setdefault(built_from["name"], set()).add(text)
    assert all(len(found) == 1 for found in texts.values())
    assert len({text for found in texts.values() for text in found}) == len(texts)


def test_every_override_is_applied() -> None:
    # An override is about an upstream case. Where the corpus has one case for several of
    # them, that case has the notes of all, and the label of each direction from whichever
    # of them gives one; so a label that an override leaves open may come from another.
    overrides = Overrides.read(ROOT / "overrides.json").overrides
    by_id = {case.id: case for case in cases()}
    not_applied = []
    for case_id, override in overrides.items():
        if (case := by_id.get(case_id)) is None:
            continue
        stated = (
            (override.a_subsumes_b, case.a_subsumes_b),
            (override.b_subsumes_a, case.b_subsumes_a),
        )
        if override.note not in (case.note or "") or any(
            label is not None and label != given for label, given in stated
        ):
            not_applied.append(case_id)
    assert not_applied == []
    assert len(overrides.keys() & by_id.keys()) > 30
    # Every note is that of an override, and the note of every override is in the corpus.
    assert {case.note for case in cases() if case.note is not None} == {
        override.note for override in overrides.values()
    }


def test_no_excluded_case_is_in_the_corpus() -> None:
    exclusions = Overrides.read(ROOT / "overrides.json").exclusions
    assert [case.id for case in cases() if exclusion_of(case.id, exclusions) is not None] == []
