"""The two transformations of the build: splitting a fused test and converting to 2020-12."""

from dataclasses import replace
from pathlib import Path

import pytest

from subsumes_benchmark import Json
from subsumes_benchmark.build import (
    Case,
    ConfigError,
    Overrides,
    Source,
    SourceSpec,
    build,
    bundled,
    overridden,
    source_label,
    without_duplicates,
    without_excluded,
    write_json,
)
from subsumes_benchmark.convert import DRAFT_2020_12, ConversionError, Converter
from subsumes_benchmark.families import pigeonhole
from subsumes_benchmark.generated.case import CounterexampleLabel, OverrideLabel, SourceLabel
from subsumes_benchmark.generated.collections import Forge
from subsumes_benchmark.generated.overrides import Override
from subsumes_benchmark.unfuse import unfuse


def convert(schema: Json) -> Json:
    converter = Converter()
    return converter.rewrite_refs(converter.convert(schema), {})


def test_building_a_generated_collection_needs_no_source(tmp_path: Path) -> None:
    collections = tmp_path / "collections.json"
    overrides = tmp_path / "overrides.json"
    derived = tmp_path / "derived.json"
    write_json(
        collections,
        {
            "$schema": "./schemas/collections.schema.json",
            "sources": {},
            "origins": {
                "example": {"short": "Example", "citation": "Example", "url": "https://example.org"}
            },
            "collections": {
                "scaling-families": {
                    "origin": "example",
                    "generator": "families",
                    "labels": "by-construction",
                    "use_case": "tool-checking",
                    "description": "Generated scaling cases.",
                }
            },
        },
    )
    write_json(
        overrides, {"$schema": "./schemas/overrides.schema.json", "exclude": [], "override": []}
    )
    write_json(derived, {"$schema": "./schemas/derived.schema.json", "cases": {}})

    corpus = tmp_path / "corpus"
    build(corpus, collections, overrides, derived)

    generated = corpus / "example" / "scaling-families"
    assert (generated / "pigeonhole.holes2.json").is_file()
    assert (generated / "pigeonhole.holes2.twin.json").is_file()


def test_array_items_become_prefix_items_and_references_follow() -> None:
    assert convert(
        {
            "items": [{"type": "string"}, {"$ref": "#/items/0"}],
            "additionalItems": {"$ref": "#/definitions/tail"},
            "definitions": {"tail": {"type": "integer"}},
        }
    ) == {
        "$schema": DRAFT_2020_12,
        "prefixItems": [{"type": "string"}, {"$ref": "#/prefixItems/0"}],
        "items": {"$ref": "#/$defs/tail"},
        "$defs": {"tail": {"type": "integer"}},
    }


def test_dependencies_split_by_kind() -> None:
    assert convert({"dependencies": {"a": ["b"], "c": {"required": ["d"]}}}) == {
        "$schema": DRAFT_2020_12,
        "dependentRequired": {"a": ["b"]},
        "dependentSchemas": {"c": {"required": ["d"]}},
    }


def test_boolean_exclusive_bounds_become_numeric() -> None:
    assert convert(
        {"minimum": 1, "exclusiveMinimum": True, "maximum": 5, "exclusiveMaximum": False}
    ) == {
        "$schema": DRAFT_2020_12,
        "exclusiveMinimum": 1,
        "maximum": 5,
    }


def test_identifiers_are_dropped_except_an_absolute_root_id() -> None:
    assert convert(
        {
            "id": "http://example.com/root.json",
            "properties": {"a": {"id": "#named"}, "b": {"id": "nested.json", "$ref": "other.json"}},
        }
    ) == {
        "$schema": DRAFT_2020_12,
        "$id": "http://example.com/root.json",
        "properties": {
            "a": {"$anchor": "named"},
            # A reference to another document is absolutised and gets an empty fragment.
            "b": {"$ref": "http://example.com/other.json#"},
        },
    }


def test_keywords_of_draft_2019_09_recursion_are_refused() -> None:
    with pytest.raises(ConversionError):
        convert({"$recursiveRef": "#"})


def test_unfuse_restores_both_sides_with_the_definitions_they_use() -> None:
    first: Json = {"$ref": "#/definitions1/x"}
    second: Json = {"$ref": "#/definitions3/y"}
    fused: Json = {
        "allOf": [
            {"properties": {"p": {"$ref": "#/allOf/0/properties/q"}, "q": first}},
            {"not": {"items": second, "not": {"$ref": "#/allOf/1/not"}}},
        ],
        "definitions1": {"x": {"type": "object"}},
        "definitions3": {"y": {"type": "integer"}},
        "anyOf": [first, {"not": first}, second, {"not": second}],
    }
    assert unfuse(fused) == (
        {
            "properties": {"p": {"$ref": "#/properties/q"}, "q": {"$ref": "#/definitions1/x"}},
            "definitions1": {"x": {"type": "object"}},
        },
        {
            "items": {"$ref": "#/definitions3/y"},
            "not": {"$ref": "#"},
            "definitions3": {"y": {"type": "integer"}},
        },
        {"top-level tautology anyOf dropped"},
    )


def test_unfuse_refuses_what_the_artifact_does_not_emit() -> None:
    with pytest.raises(ConversionError):
        unfuse({"allOf": [{}, {}]})
    with pytest.raises(ConversionError):
        unfuse({"allOf": [{}, {"not": {}}], "title": "extra"})


@pytest.mark.parametrize(
    ("forge", "link"),
    [
        ("github", "https://example.com/group/suite/blob/abc123/tests/a%20b/c.json"),
        ("gitlab", "https://example.com/group/suite/-/blob/abc123/tests/a%20b/c.json"),
    ],
)
def test_a_permalink_names_the_commit_in_the_way_of_the_forge(forge: Forge, link: str) -> None:
    root = Path("sources/suite")
    source = Source(
        name="suite",
        spec=SourceSpec(forge=forge, license="MIT", license_file="LICENSE"),
        root=root,
        repository="https://example.com/group/suite.git",
        commit="abc123",
    )
    assert source.permalink(root / "tests" / "a b" / "c.json") == link


def test_a_case_names_its_schema_and_says_what_is_known_before_the_schemas() -> None:
    case = Case(
        id="one/two/three",
        a=True,
        b={"type": "string"},
        a_subsumes_b=source_label(True),
        b_subsumes_a=None,
        upstream="x.json",
    )
    document = case.document
    assert isinstance(document, dict)
    assert list(document) == [
        "$schema",
        "labels",
        "built_from",
        "features",
        "a",
        "b",
    ]
    assert document["labels"] == {
        "a_subsumes_b": {"kind": "source", "answer": True},
        "b_subsumes_a": None,
    }
    assert document["built_from"] == {"kind": "source", "link": "x.json"}
    assert document["$schema"] == "../../case.schema.json"
    assert (document["a"], document["b"], document["features"]) == (True, case.b, ["type"])


def test_excluded_cases_are_left_out_and_must_exist() -> None:
    cases = [
        Case(case_id, True, True, source_label(True), None, upstream="x.json")
        for case_id in ("o/one/a", "o/one/b")
    ]
    assert [case.id for case in without_excluded(cases, {"o/one/a": "broken"})] == ["o/one/b"]
    assert without_excluded(cases, {}) == cases
    with pytest.raises(ConfigError):
        without_excluded(cases, {"o/one/c": "broken"})


def test_the_beginning_of_a_name_excludes_every_case_whose_name_begins_so() -> None:
    ids = (
        "o/one/a.3.valid.0",
        "o/one/a.3.reflexive",
        "o/one/a.30.reflexive",
        "o/one/ab.3.reflexive",
        "o/two/a.3.reflexive",
    )
    cases = [
        Case(case_id, True, True, source_label(True), None, upstream="x.json") for case_id in ids
    ]
    assert [case.id for case in without_excluded(cases, {"o/one/a.3.*": "broken"})] == list(ids[2:])
    assert [case.id for case in without_excluded(cases, {"o/one/a.*": "broken"})] == list(ids[3:])
    with pytest.raises(ConfigError):
        without_excluded(cases, {"o/three/a.*": "broken"})
    # A beginning ends at a dot of the name, and neither a whole name nor a folder is one.
    with pytest.raises(ConfigError):
        without_excluded(cases, {"o/one/a.3.refl.*": "broken"})
    with pytest.raises(ConfigError):
        without_excluded(cases, {"o/one/a.3.reflexive.*": "broken"})
    with pytest.raises(ConfigError):
        without_excluded(cases, {"o/one/*": "broken"})


def a_case(
    case_id: str,
    a: Json,
    b: Json,
    a_subsumes_b: bool | None = None,
    b_subsumes_a: bool | None = None,
    note: str | None = None,
) -> Case:
    labels = source_label(a_subsumes_b), source_label(b_subsumes_a)
    return Case(case_id, a, b, *labels, f"{case_id}.json", note)


TEXT: Json = {"type": "string"}
OPTIONAL: Json = {"type": ["string", "null"]}
NUMBER: Json = {"type": "number"}


def test_cases_with_the_same_two_schemas_are_one_case_that_says_what_each_says() -> None:
    cases = [
        # Asked in both directions, as two cases: the second is the first one the other way.
        a_case("o/one/x_v2_not_v1", OPTIONAL, TEXT, True),
        a_case("o/one/x_v1_not_v2", TEXT, OPTIONAL, False),
        # Asked twice the same way; only the one that is not kept knows the answer.
        a_case("o/one/b", TEXT, NUMBER, None, None),
        a_case("o/two/b", TEXT, NUMBER, False, False, note="Corrected."),
        a_case("o/one/alone", NUMBER, OPTIONAL, False),
    ]
    kept = without_duplicates(cases)
    assert [case.id for case in kept] == ["o/one/x_v1_not_v2", "o/one/b", "o/one/alone"]
    both, twice, alone = kept
    assert both.answers == (False, True)
    # An answer that another upstream file gives links to it.
    assert both.a_subsumes_b == SourceLabel(kind="source", answer=False)
    assert both.b_subsumes_a == SourceLabel(
        kind="source", answer=True, link="o/one/x_v2_not_v1.json"
    )
    assert both.duplicates == ("o/one/x_v2_not_v1.json",)
    assert (*twice.answers, twice.note) == (False, False, "Corrected.")
    assert twice.duplicates == ("o/two/b.json",)
    assert alone is cases[4]
    written = both.document
    assert isinstance(written, dict)
    assert written["built_from"] == {
        "kind": "source",
        "link": both.upstream,
        "duplicates": ["o/one/x_v2_not_v1.json"],
    }
    # The order the cases come in decides nothing.
    assert without_duplicates(cases[::-1]) == kept[::-1]


def test_the_case_whose_id_sorts_first_is_kept() -> None:
    cases = [
        a_case(case_id, TEXT, NUMBER)
        for case_id in ("o/two/a", "o/one/b.2", "o/one/b.10", "o/one/c")
    ]
    (kept,) = without_duplicates(cases)
    # Sorted as the cases of the corpus are: by folder, then by name.
    assert kept.id == "o/one/b.10"
    assert kept.duplicates == ("o/one/b.2.json", "o/one/c.json", "o/two/a.json")


def test_a_case_whose_two_schemas_are_the_same_keeps_the_label_of_each_direction() -> None:
    cases = [a_case("o/one/a", TEXT, TEXT, True), a_case("o/one/b", TEXT, TEXT, None, True)]
    (kept,) = without_duplicates(cases)
    assert kept.answers == (True, True)
    # Its own label for one direction is not taken for the other, though they are one question.
    (alone,) = without_duplicates([cases[0]])
    assert alone.answers == (True, None)
    (still,) = without_duplicates([cases[0], a_case("o/one/c", TEXT, TEXT, True)])
    assert still.answers == (True, None)
    # Its own answer is the one it keeps, with no link to the other file that gives it too.
    assert still.a_subsumes_b == SourceLabel(kind="source", answer=True)


def test_duplicates_that_come_from_one_upstream_file_list_it_once_and_not_their_own() -> None:
    same_file = [
        Case("o/one/a", TEXT, NUMBER, None, None, "x.json#/0"),
        Case("o/one/b", TEXT, NUMBER, None, None, "x.json#/0"),
        Case("o/one/c", NUMBER, TEXT, None, None, "x.json#/1"),
        Case("o/one/d", NUMBER, TEXT, None, None, "x.json#/1"),
    ]
    (kept,) = without_duplicates(same_file)
    assert kept.duplicates == ("x.json#/1",)


def test_duplicates_must_not_contradict_each_other() -> None:
    with pytest.raises(ConversionError, match="two answers"):
        without_duplicates(
            [a_case("o/one/a", TEXT, NUMBER, True), a_case("o/one/b", TEXT, NUMBER, False)]
        )
    with pytest.raises(ConversionError, match="two answers"):
        without_duplicates(
            [a_case("o/one/a", TEXT, NUMBER, True), a_case("o/one/b", NUMBER, TEXT, None, False)]
        )
    # Two notes are both kept.
    (kept,) = without_duplicates(
        [
            a_case("o/one/a", TEXT, NUMBER, note="First."),
            a_case("o/one/b", NUMBER, TEXT, note="Second."),
        ]
    )
    assert kept.note == "First. Second."


def test_a_generated_case_says_what_it_was_generated_from_in_place_of_a_link() -> None:
    (member, twin) = pigeonhole(2)
    labels = member.label("a_subsumes_b"), member.label("b_subsumes_a")
    case = Case("o/families/x", member.a, member.b, *labels, None, generated=member.generated)
    document = case.document
    assert isinstance(document, dict)
    assert document["built_from"] == {
        "kind": "generator",
        "family": "pigeonhole",
        "sizes": {"holes": 2},
        "twin": False,
    }
    # A case comes from upstream or is generated, and not both or neither.
    with pytest.raises(ValueError, match="upstream or is generated"):
        Case("o/one/x", TEXT, NUMBER, None, None, None)
    with pytest.raises(ValueError, match="upstream or is generated"):
        replace(case, upstream="x.json")
    assert document["labels"] == {
        "a_subsumes_b": {"kind": "construction", "answer": True},
        "b_subsumes_a": {"kind": "construction", "answer": True},
    }
    # A twin's false label holds the counterexample that the generator gave.
    shown = twin.label("a_subsumes_b")
    assert shown == CounterexampleLabel(
        kind="counterexample", answer=False, instance=twin.counterexamples["a_subsumes_b"]
    )
    # What the schema of a case does not say of a generated case, the build holds to.
    for departure in (
        {"b_subsumes_a": None},
        {"b_subsumes_a": source_label(True)},
        {"note": "Corrected."},
        {"duplicates": ("y",)},
    ):
        with pytest.raises(ValueError, match="both labels as it built them"):
            replace(case, **departure)


def test_an_override_is_a_label_of_its_own_where_it_departs_from_the_source() -> None:
    case = a_case("o/one/a", TEXT, NUMBER, True, None)
    entry = Override(note="Corrected.", a_subsumes_b=False, b_subsumes_a=False, cases=["o/one/a"])
    (changed,) = overridden([case], {"o/one/a": entry})
    assert changed.a_subsumes_b == OverrideLabel(kind="override", answer=False)
    assert changed.b_subsumes_a == OverrideLabel(kind="override", answer=False)
    assert changed.note == "Corrected."
    # Where it states what the source says, the label is still the source's, and where it
    # claims nothing, there is none.
    agreeing = Override(note="Withdrawn.", a_subsumes_b=True, b_subsumes_a=None, cases=["o/one/a"])
    (kept,) = overridden([case], {"o/one/a": agreeing})
    assert (kept.a_subsumes_b, kept.b_subsumes_a) == (case.a_subsumes_b, None)


def test_a_generated_case_has_no_duplicate() -> None:
    (member, _) = pigeonhole(2)
    labels = member.label("a_subsumes_b"), member.label("b_subsumes_a")
    generated = Case("o/families/x", TEXT, NUMBER, *labels, None, generated=member.generated)
    with pytest.raises(ConversionError, match="generated cases have the schemas of others"):
        without_duplicates([generated, a_case("o/one/a", NUMBER, TEXT)])


def overrides_file(folder: Path, exclude: Json, override: Json) -> Path:
    file = folder / "overrides.json"
    schema = "./schemas/overrides.schema.json"
    write_json(file, {"$schema": schema, "exclude": exclude, "override": override})
    return file


def test_exclusions_and_overrides_are_read_by_case(tmp_path: Path) -> None:
    corrected = {"note": "corrected", "a_subsumes_b": False, "b_subsumes_a": None}
    departures = Overrides.read(
        overrides_file(
            tmp_path,
            [{"reason": "broken", "cases": ["o/one/a", "o/one/b.*"]}],
            [{**corrected, "cases": ["o/one/c"]}],
        )
    )
    assert departures.exclusions == {"o/one/a": "broken", "o/one/b.*": "broken"}
    assert departures.overrides.keys() == {"o/one/c"}
    override = departures.overrides["o/one/c"]
    assert (override.note, override.a_subsumes_b, override.b_subsumes_a) == (
        "corrected",
        False,
        None,
    )


@pytest.mark.parametrize(
    ("exclude", "override"),
    [
        # A case is listed once: not twice in an entry, and not left out and overridden.
        ([{"reason": "broken", "cases": ["o/one/a", "o/one/a"]}], []),
        (
            [{"reason": "broken", "cases": ["o/one/a"]}],
            [{"note": "x", "a_subsumes_b": None, "b_subsumes_a": None, "cases": ["o/one/a"]}],
        ),
        # An override states both labels, and nothing has a key that is not known.
        ([], [{"note": "x", "a_subsumes_b": None, "cases": ["o/one/a"]}]),
        ([{"reason": "broken", "note": "x", "cases": ["o/one/a"]}], []),
        # A case is a name in the folder of a collection of an origin, and an entry lists one.
        ([{"reason": "broken", "cases": ["one/a"]}], []),
        ([{"reason": "broken", "cases": ["o/one/a/b"]}], []),
        ([{"reason": "broken", "cases": []}], []),
    ],
)
def test_overrides_that_are_not_what_the_model_says_are_not_read(
    tmp_path: Path, exclude: Json, override: Json
) -> None:
    with pytest.raises(ConfigError):
        Overrides.read(overrides_file(tmp_path, exclude, override))


def test_a_name_in_a_map_of_schemas_is_not_taken_for_a_keyword() -> None:
    # `default`, `enum` and `const` are names here, so what they hold are schemas. The
    # keyword `default` at the top holds data, which stays as it is.
    assert convert(
        {
            "definitions": {"const": {"$ref": "#/definitions/x"}, "x": {"type": "string"}},
            "properties": {
                "default": {"$ref": "#/definitions/x"},
                "enum": {"items": [{"$ref": "#/definitions/const"}]},
            },
            "default": {"$ref": "#/definitions/x"},
        }
    ) == {
        "$schema": DRAFT_2020_12,
        "$defs": {"const": {"$ref": "#/$defs/x"}, "x": {"type": "string"}},
        "properties": {
            "default": {"$ref": "#/$defs/x"},
            "enum": {"prefixItems": [{"$ref": "#/$defs/const"}]},
        },
        "default": {"$ref": "#/definitions/x"},
    }


def test_unfuse_follows_references_under_names_that_read_like_keywords() -> None:
    fused: Json = {
        "allOf": [
            {"properties": {"default": {"$ref": "#/definitions1/enum"}, "q": {}}},
            {"not": {"properties": {"const": {"$ref": "#/allOf/1/not/properties/q"}, "q": {}}}},
        ],
        "definitions1": {"enum": {"$ref": "#/definitions2/x"}},
        "definitions2": {"x": {"type": "object"}},
    }
    assert unfuse(fused) == (
        {
            "properties": {"default": {"$ref": "#/definitions1/enum"}, "q": {}},
            "definitions1": {"enum": {"$ref": "#/definitions2/x"}},
            "definitions2": {"x": {"type": "object"}},
        },
        {"properties": {"const": {"$ref": "#/properties/q"}, "q": {}}},
        set(),
    )


DOCUMENTS: dict[str, Json] = {
    "https://example.com/name.json": {"$id": "https://example.com/name.json", "type": "string"},
    "https://example.com/person.json": {
        "$id": "https://example.com/person.json",
        "properties": {
            "name": {"$ref": "name.json"},
            "friend": {"$ref": "team.json#/$defs/member"},
        },
    },
    "https://example.com/team.json": {
        "$id": "https://example.com/team.json",
        "$defs": {"member": {"$ref": "person.json"}},
    },
    "https://example.com/unused.json": {"$id": "https://example.com/unused.json"},
}


def test_a_schema_carries_every_document_it_reaches() -> None:
    schema: Json = {
        "$id": "https://example.com/root.json",
        "items": {"$ref": "person.json"},
        "$defs": {"local": {"type": "null"}},
    }
    assert bundled(schema, DOCUMENTS) == {
        "$id": "https://example.com/root.json",
        "items": {"$ref": "person.json"},
        "$defs": {
            "local": {"type": "null"},
            "https://example.com/name.json": DOCUMENTS["https://example.com/name.json"],
            "https://example.com/person.json": DOCUMENTS["https://example.com/person.json"],
            "https://example.com/team.json": DOCUMENTS["https://example.com/team.json"],
        },
    }
    # The schema given is not changed.
    assert schema["$defs"] == {"local": {"type": "null"}}


def test_a_schema_that_references_no_document_stays_as_it_is() -> None:
    schemas: list[Json] = [
        True,
        {"$ref": "#/$defs/a", "$defs": {"a": {}}},
        {"$ref": "https://other.example/x"},
    ]
    for schema in schemas:
        assert bundled(schema, DOCUMENTS) is schema


def test_the_url_of_the_schema_itself_is_the_schema() -> None:
    # Two versions of a document are compared under one URL, and a document that both reach
    # refers back to that URL. The reference is to the version at hand, which is not embedded.
    schema: Json = {
        "$id": "https://example.com/person.json",
        "properties": {"friend": {"$ref": "team.json#/$defs/member"}},
    }
    assert bundled(schema, DOCUMENTS) == schema | {
        "$defs": {"https://example.com/team.json": DOCUMENTS["https://example.com/team.json"]}
    }


def test_a_document_must_carry_its_url() -> None:
    documents: dict[str, Json] = {"https://example.com/a.json": {"type": "string"}}
    with pytest.raises(ConversionError):
        bundled({"$ref": "https://example.com/a.json"}, documents)
