"""The committed corpus has the layout the README describes."""

import tomllib

from jsonschema import Draft202012Validator

from reading import CORPUS, ROOT, cases, read
from subsumes_benchmark.build import CASE_SCHEMA, load_exclusions, load_overrides

CASE_FILES = {"a.json", "b.json", "case.json"}
CONFIG = tomllib.loads((ROOT / "collections.toml").read_text(encoding="utf-8"))
COLLECTIONS = CONFIG["collections"]
LICENSES = {f"{name}.txt" for name in (*CONFIG["sources"], "json-schema-test-suite")}


def test_every_case_has_both_schemas() -> None:
    incomplete = [
        case.id
        for case in cases()
        if not ((case.folder / "a.json").is_file() and (case.folder / "b.json").is_file())
    ]
    assert incomplete == []


def test_every_file_belongs_to_a_case_or_is_a_shared_file() -> None:
    folders = {case.folder for case in cases()}
    shared = (
        {CORPUS / "case.schema.json", CORPUS / "resources.json"}
        | {CORPUS / name / "collection.json" for name in COLLECTIONS}
        | {CORPUS / "licenses" / name for name in LICENSES}
    )
    stray = [
        path.relative_to(CORPUS).as_posix()
        for path in CORPUS.rglob("*")
        if path.is_file()
        and path not in shared
        and not (path.parent in folders and path.name in CASE_FILES)
    ]
    assert stray == []


def test_every_case_matches_the_case_schema() -> None:
    assert read(CORPUS / "case.schema.json") == CASE_SCHEMA
    validator = Draft202012Validator(CASE_SCHEMA)
    invalid = {
        case.id: [error.message for error in validator.iter_errors(read(case.folder / "case.json"))]
        for case in cases()
    }
    assert {case_id: errors for case_id, errors in invalid.items() if errors} == {}


def test_every_collection_has_its_manifest() -> None:
    assert {path.name for path in CORPUS.iterdir() if path.is_dir()} == {*COLLECTIONS, "licenses"}
    assert {case.collection for case in cases()} == set(COLLECTIONS)
    for name, spec in COLLECTIONS.items():
        manifest = read(CORPUS / name / "collection.json")
        assert isinstance(manifest, dict)
        source = manifest.pop("source")
        assert isinstance(source, dict)
        assert manifest == {
            "description": spec["description"],
            "use_case": spec["use-case"],
            "labels": spec["labels"],
            "license": CONFIG["sources"][spec["source"]]["license"],
            "license_file": f"licenses/{spec['source']}.txt",
        }
        assert source["path"] == spec["path"]
        assert source.keys() == {"repository", "commit", "path"}


def test_every_license_is_there() -> None:
    assert {path.name for path in (CORPUS / "licenses").iterdir()} == LICENSES


def test_every_override_is_applied() -> None:
    overrides = load_overrides(ROOT / "overrides.toml")
    by_id = {case.id: case for case in cases()}
    assert sorted(overrides.keys() - by_id.keys()) == []
    not_applied = [
        case_id
        for case_id, override in overrides.items()
        if (by_id[case_id].a_subsumes_b, by_id[case_id].b_subsumes_a, by_id[case_id].note)
        != (override.a_subsumes_b, override.b_subsumes_a, override.note)
    ]
    assert not_applied == []
    assert [case.id for case in cases() if case.note is not None and case.id not in overrides] == []


def test_no_excluded_case_is_in_the_corpus() -> None:
    exclusions = load_exclusions(ROOT / "overrides.toml")
    assert sorted(exclusions.keys() & {case.id for case in cases()}) == []
