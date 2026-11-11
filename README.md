# subsumes-benchmark

A benchmark corpus for JSON Schema inclusion: **does schema A accept every instance valid under schema B?**

It holds 14,614 pairs of draft 2020-12 schemas, most of them with a known answer. They come from the two public benchmarks for this problem, converted to draft 2020-12 where they were not already, and are stored as one folder per case. The corpus is what [`subsumes`](https://github.com/georg-wolflein/subsumes) is measured against, but nothing in it depends on that library.

## A case

```
corpus/schemastore-versions/agripparc-1.2_v2_not_v1/
├── a.json
├── b.json
└── case.json
```

Every case asks the same question: does `a.json` accept every instance valid under `b.json`? If it does, A subsumes B. A folder is a case exactly when it contains `case.json`, and its path below `corpus/` is its id.

`a.json` and `b.json` are plain schemas, indented, with every non-ASCII character escaped so that none is invisible. `case.json` says what is known:

```json
{
  "a_subsumes_b": false,
  "b_subsumes_a": null,
  "upstream": "src/test/resources/inclusion/schemastore_containment/sat/agripparc-1.2_v2_not_v1.json"
}
```

- **`a_subsumes_b`**: `true` when `a.json` accepts every instance valid under `b.json`, `false` when some instance of `b.json` is not valid under `a.json`, `null` when the corpus claims nothing.
- **`b_subsumes_a`**: The same question in the other direction. Only some cases of the containment test suite answer it.
- **`upstream`**: The file the case comes from, as a path inside the source repository that the collection's `collection.json` names. The test suite's cases add the case id after a `#`.
- **`note`**: Present only when the labels depart from upstream's, and says why.

[`corpus/case.schema.json`](corpus/case.schema.json) is the schema of `case.json`.

## What the labels mean

A label holds under these semantics:

- **Draft 2020-12.**
- **`format` is asserted**, not treated as an annotation.
- **Patterns are read in the dialect of the Rust [`regex`](https://docs.rs/regex/latest/regex/#syntax) crate**, which is what [Pydantic](https://docs.pydantic.dev/) validates `pattern` with by default. This is not ECMA-262: `\d`, `\w` and `\s` are Unicode-aware, and look-around and backreferences do not exist.

Where an upstream label does not hold under these semantics, the corpus corrects it or withdraws it; see [Departures from upstream](#departures-from-upstream).

## Scoring a checker

Run every case whose `a_subsumes_b` is not `null`, and `b_subsumes_a` likewise where it is given:

- A checker is **wrong** when it answers yes and the label is `false`, or no and the label is `true`.
- Declining to answer is never wrong. How often a checker declines, and how long it takes, can be measured on every case, including those labelled `null`.

Some schemas reference other documents. [`corpus/resources.json`](corpus/resources.json) maps each URL to its document; register all of them before checking. The URLs are `http://localhost:1234/...` for the test suite's remotes and `https://raw.githubusercontent.com/...` for the documents that `rb-testset` uses.

## Releases

A release is a tag `v<version>` that carries one file, `corpus.tar.zst`: the `corpus/` folder as a tar archive compressed with Zstandard, about 4 MB.

```bash
curl -fsSLO https://github.com/georg-wolflein/subsumes-benchmark/releases/download/v0.1.0/corpus.tar.zst
zstd -dc corpus.tar.zst | tar -xf -   # unpacks into corpus/
```

The release notes give the SHA-256 of the file. The version says what a change means for someone who measures a checker:

- **Major**: A reader has to change, because the layout, the fields of `case.json`, the form of the case ids or the semantics of the labels changed.
- **Minor**: Results are no longer comparable, because cases were added or removed, or a label or a schema changed.
- **Patch**: Anything else, such as notes, descriptions, documentation and code.

Results measured on two versions are comparable exactly when their major and minor numbers match. Before 1.0.0, a minor version may also bring what a major version would.

## Collections

| Collection | Cases | A subsumes B: true / false / unknown | Labels from | Content |
| --- | --- | --- | --- | --- |
| `containment-testsuite` | 3,343 | 1,870 / 1,374 / 99 | construction | The Passau containment test suite for draft 2020-12 |
| `synthesized` | 1,331 | 881 / 450 / 0 | construction | The same generator for drafts 4, 6 and 2019-09, converted |
| `handwritten-sc` | 282 | 160 / 122 / 0 | construction | Hand-written hard cases |
| `rb-testset` | 300 | 107 / 189 / 4 | upstream tests | The tests of the jsonsubschema tool, with external references |
| `mergeallof` | 174 | 165 / 9 / 0 | witness generator | Schemas against a rewriting that merges their `allOf` |
| `schemastore-versions` | 1,056 | 0 / 153 / 903 | witness generator | Successive versions of real schemas |
| `oneof-as-anyof` | 1,822 | 0 / 146 / 1,676 | witness generator | Is `oneOf` used where `anyOf` would be equivalent? |
| `uneval-as-additional` | 608 | 0 / 179 / 429 | witness generator | `unevaluated*` against a translation to `additional*` |
| `additional-as-uneval` | 5,698 | 5,413 / 139 / 146 | witness generator | `additional*` against a rewriting through `unevaluated*` |

Each collection folder has a `collection.json` with its description, the source repository and commit, the licence, and where its labels come from:

- **`by-construction`**: The pair was built so that the answer is known.
- **`witness-generator`**: The answer is that of the upstream authors' tool, which is complete but bound by a timeout. An unknown label means that it gave up.
- **`upstream-tests`**: The expectations of the jsonsubschema tool's own tests.

The path of a case in `containment-testsuite` is `<category>/<keyword>/<number>`, with `optional/` before the keyword for the cases the official suite marks optional. `synthesized` has the draft in front: `draft4/valid/minimum/3`. The category says how the pair was built from a schema S of the official JSON Schema Test Suite:

- **`valid`**: B is a `const` of one of the suite's instances and A is S.
- **`nonvalid`**: The same instance against `not S`.
- **`unions`**: B is an `anyOf` of several instances and A is S.
- **`reflexive`**: S against itself.
- **`universal`**: `anyOf: [S, not S]` against `true`.
- **`unsatisfiable`**: `allOf: [S, not S]` against `false`.

`synthesized` is largely a near-duplicate of `containment-testsuite`, so a report should not add the two up.

## Departures from upstream

[`overrides.toml`](overrides.toml) lists every case whose labels differ from upstream's, with the reason, which is copied into the case's `note`. There are 171 such cases:

| Reason | Cases | What the corpus does |
| --- | --- | --- |
| A schema is not valid draft 2020-12, or a reference in it does not resolve | 8 | Claims nothing |
| A pattern is not valid in the Rust regex dialect | 50 | Claims nothing |
| Upstream's label does not hold | 32 | Corrects 4, claims nothing for 28 |
| Upstream's label holds only if `format` is an annotation | 63 | Claims nothing |
| Upstream's label depends on the regex dialect | 18 | Corrects all 18 |

Two limits remain:

- **Patterns.** 6,048 labelled cases use patterns. In 291 of them `b.json` only lists its instances, so the label can be checked by validating those instances against `a.json`; the tests do that with Rust regex matching, for these and for 2,080 such cases without patterns. The other 5,757 labels come from upstream tools that read patterns in their own dialect. They are kept as they are until a checker disagrees and the dialect turns out to be the reason.
- **Formats.** Upstream's witness generator asserts only a few formats. A label of a `witness-generator` collection that hinges on a format may therefore not hold with every format asserted; six such cases are known and listed.

## How the sources are converted

The containment test suite is taken as it is. The inclusion artifact stores each test as one fused document, `{"allOf": [S1, {"not": S2}]}`, with both sides' definitions hoisted to the top level, every other pointer prefixed with its path in the fused document, and the answer given by the directory (`sat`, `unsat` or `unknown`). The build undoes each step and then converts each side to draft 2020-12:

- `definitions` and the hoisted groups become one `$defs`.
- Array-form `items` becomes `prefixItems`, and `additionalItems` becomes `items`.
- `dependencies` splits into `dependentRequired` and `dependentSchemas`.
- A draft-04 `id: "#name"` becomes `$anchor`; other identifiers are dropped, except an absolute root `$id`. Both upstream tools resolve `#/...` pointers against the document root, which is what a draft 2020-12 document without embedded resources does.
- Every JSON-pointer reference is mapped to where its target moved, so `#/items/0` becomes `#/prefixItems/0`.
- Unknown keywords and `format` are kept as written.

Both upstream sources list the narrower schema first, so `b.json` is upstream's first schema and `a.json` its second. In `agripparc-1.2_v2_not_v1`, `b.json` is version 2 and `a.json` is version 1.

## Repository layout

| Path | Content |
| --- | --- |
| `corpus/` | The corpus: generated, committed, never edited by hand |
| `collections.toml` | The collections and the upstream dataset each is built from |
| `overrides.toml` | Every departure from an upstream label, with the reason |
| `sources/` | The upstream repositories as submodules, fetched only to rebuild |
| `src/subsumes_benchmark/` | The build: `unfuse`, `convert`, `build` |
| `tests/` | The layout of the corpus, the validity of its schemas, the labels that can be checked |

## Rebuilding the corpus

```bash
uv sync
make sources   # fetches the two upstream repositories, about 900 MB
make corpus    # about 15 seconds
```

The submodules under `sources/` are marked `update = none`, so cloning this repository, even recursively, does not fetch them; `make sources` does. Their commits pin what the corpus is built from. The build needs nothing but the standard library.

## Development

```bash
uv sync
make ci            # ruff check, ruff format --check, ty check, pytest
make test-corpus   # the slow tests over every schema, about three minutes
make format        # apply ruff's fixes and formatting
```

CI runs both on every push and pull request. The slow tests check that every schema is valid draft 2020-12, that every reference resolves, and that every label that validation can check holds.

To publish a release:

```bash
uv version --bump minor   # or major or patch; commit the change to main
make release              # tags that commit v<version> and pushes the tag
```

The `Release` workflow then runs every check on the tagged commit, builds the archive and publishes the release. Not every commit on `main` is released.

## Credits and licences

The code in this repository is MIT licensed. The corpus keeps the licences of its sources, which each `collection.json` names; the licence texts are in [`corpus/licenses/`](corpus/licenses).

`containment-testsuite` comes from [sdbs-uni-p/json-schema-containment-testsuite](https://github.com/sdbs-uni-p/json-schema-containment-testsuite) (MIT, Stefanie Scherzinger, University of Passau), described in Lyes Attouche, Mohamed-Amine Baazizi, Dario Colazzo, Yunchen Ding, Michael Fruth, Giorgio Ghelli, Carlo Sartiani and Stefanie Scherzinger, *A Test Suite for JSON Schema Containment*, ER 2021 Demos and Posters, CEUR Workshop Proceedings 2958. Its `$ref` cases load the `remotes/` of [json-schema-org/JSON-Schema-Test-Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite) (MIT, Julian Berman), which are in `resources.json`.

The eight other collections come from the artifact of Mohamed-Amine Baazizi, Nour El Houda Ben Ali, Dario Colazzo, Giorgio Ghelli, Stefan Klessinger, Carlo Sartiani and Stefanie Scherzinger, *JSON Schema Inclusion through Refutational Normalization: Reconciling Efficiency and Completeness* ([arXiv:2603.25306](https://arxiv.org/abs/2603.25306), 2026), at [gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema), GPL-3.0. Five of them were assembled for *Witness Generation for JSON Schema* (Lyes Attouche, Mohamed-Amine Baazizi, Dario Colazzo, Giorgio Ghelli, Carlo Sartiani and Stefanie Scherzinger, PVLDB 15(13), 2022; reproduction package [sdbs-uni-p/JSONSchemaWitnessGeneration](https://github.com/sdbs-uni-p/JSONSchemaWitnessGeneration)) and *Witness Generation for Classical JSON Schema* (same authors, ACM TODS 51(4), 2026). The schemas inside come from [IBM/jsonsubschema](https://github.com/IBM/jsonsubschema)'s tests (Apache-2.0; Andrew Habib, Avraham Shinnar, Martin Hirzel and Michael Pradel, *Finding Data Compatibility Bugs with JSON Subschema Checking*, ISSTA 2021), from [SchemaStore](https://github.com/SchemaStore/schemastore) (Apache-2.0), from the official JSON Schema Test Suite (MIT), from schemas found on GitHub, and from the authors' own hand-written cases. The external documents that `rb-testset` references (Snowplow Iglu Central and Washington Post ANS schemas) come from the artifact's cache.
