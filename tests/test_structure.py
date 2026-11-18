"""The committed corpus has the layout the README describes."""

import json

import jsonschema_rs

from reading import CORPUS, ROOT, cases, read
from subsumes_benchmark.build import Overrides, exclusion_of
from subsumes_benchmark.generated.case import CaseSpec

CONFIG = json.loads((ROOT / "collections.json").read_text(encoding="utf-8"))
COLLECTIONS = CONFIG["collections"]
LICENSES = {f"{name}.txt" for name in CONFIG["sources"]}


def test_every_file_is_a_case_or_a_shared_file() -> None:
    shared = (
        {CORPUS / "case.schema.json"}
        | {CORPUS / name / "collection.json" for name in COLLECTIONS}
        | {CORPUS / "licenses" / name for name in LICENSES}
        | {case.file for case in cases()}
    )
    stray = [
        path.relative_to(CORPUS).as_posix()
        for path in CORPUS.rglob("*")
        if path.is_file() and path not in shared
    ]
    assert stray == []


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


def test_every_upstream_is_a_permalink_into_the_dataset_of_its_collection() -> None:
    blob = {"github": "blob", "gitlab": "-/blob"}
    datasets = {}
    for name, spec in COLLECTIONS.items():
        manifest = read(CORPUS / name / "collection.json")
        assert isinstance(manifest, dict)
        source = manifest["source"]
        assert isinstance(source, dict)
        repository, commit, path = source["repository"], source["commit"], source["path"]
        assert isinstance(repository, str)
        forge = CONFIG["sources"][spec["source"]]["forge"]
        datasets[name] = f"{repository.removesuffix('.git')}/{blob[forge]}/{commit}/{path}/"
    elsewhere = [
        case.id for case in cases() if not case.upstream.startswith(datasets[case.collection])
    ]
    assert elsewhere == []


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
            "use_case": spec["use_case"],
            "labels": spec["labels"],
            "license": CONFIG["sources"][spec["source"]]["license"],
            "license_file": f"licenses/{spec['source']}.txt",
        }
        assert source["path"] == spec["path"]
        assert source.keys() == {"repository", "commit", "path"}


def test_every_license_is_there() -> None:
    assert {path.name for path in (CORPUS / "licenses").iterdir()} == LICENSES


def test_every_override_is_applied() -> None:
    overrides = Overrides.read(ROOT / "overrides.json").overrides
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
    exclusions = Overrides.read(ROOT / "overrides.json").exclusions
    assert [case.id for case in cases() if exclusion_of(case.id, exclusions) is not None] == []
