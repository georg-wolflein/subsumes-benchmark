# The corpus

Pairs of draft 2020-12 schemas, each with what is known about one question: does schema `a` accept every instance that is valid under schema `b`? If it does, A subsumes B. This folder is the whole corpus of [subsumes-benchmark](https://github.com/georg-wolflein/subsumes-benchmark). Every release carries it as `corpus.tar.zst`, and so does the package on PyPI.

## Layout

```
corpus/
├── README.md
├── case.schema.json
├── collections.json
├── habib2021/
│   └── rb-testset/
│       ├── LICENSE
│       ├── s1.json
│       └── …
├── attouche2026/
│   ├── handwritten-sc/
│   ├── mergeallof/
│   └── schemastore-versions/
├── baazizi2026/
│   ├── oneof-as-anyof/
│   ├── additional-as-uneval/
│   └── uneval-as-additional/
└── wolflein2026/
    └── json-schema-test-suite/
```

- **An origin** is the work that first published the pairs of its collections as subsumption questions, named by its first author and the year. [References](#references) has the four.
- **A collection** is a folder of cases in the folder of its origin, with the `LICENSE` they are under.
- **A case** is `<origin>/<collection>/<name>.json`, and that path without the `.json` is its id. No file lies deeper.
- **[`collections.json`](collections.json)** says of every collection what it holds, the reference of its origin, the repository and commit it is read from, its licence, and where its labels come from.
- **[`case.schema.json`](case.schema.json)** is the schema of a case.

## A case

`attouche2026/schemastore-versions/agripparc-1.2_v1_not_v2.json` holds two schemas, `a` and `b`, and what is known about them:

```json
{
  "$schema": "../../case.schema.json",
  "a_subsumes_b": true,
  "b_subsumes_a": false,
  "features": ["additionalProperties", "enum", "properties", "type"],
  "upstream": "https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema/-/blob/8064ad83a0dbdb4b02c0ce1632d273f7cbf736cf/src/test/resources/inclusion/schemastore_containment/unknown/agripparc-1.2_v1_not_v2.json",
  "duplicates": [
    "https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema/-/blob/8064ad83a0dbdb4b02c0ce1632d273f7cbf736cf/src/test/resources/inclusion/schemastore_containment/sat/agripparc-1.2_v2_not_v1.json"
  ],
  "derived": { "a_subsumes_b": { "checkers": ["RWG 8064ad8", "jsoncompat 0.6.0", "subsumes 0.2.0"] } },
  "a": { "type": "object", "additionalProperties": false, "properties": { "…": {} } },
  "b": { "type": "object", "additionalProperties": false, "properties": { "…": {} } }
}
```

A file is indented, with every non-ASCII character escaped so that none is invisible.

- **`$schema`**: The path to `case.schema.json`, the same in every case. The schemas `a` and `b` are draft 2020-12 whatever this says.
- **`a_subsumes_b`**: `true` when `a` accepts every instance valid under `b`, `false` when some instance of `b` is not valid under `a`, `null` when the corpus claims nothing.
- **`b_subsumes_a`**: The same question in the other direction.
- **`features`**: What the two schemas use; see [Features](#features).
- **`upstream`**: A permanent link to the file the case comes from, in the repository and at the commit that `collections.json` names for the collection. A case built from the test suite adds a JSON pointer to the test case or the test after a `#`.
- **`duplicates`**: Present only when upstream has these two schemas in other files too, in either order: permanent links to those files. The corpus has one case for all of them.
- **`note`**: Present only when the labels depart from upstream's, and says why.
- **`derived`**: Present only when the case has a label that upstream does not give. It names each such label with what shows it: a `counterexample` for `false`, the `checkers` that agree for `true`.
- **`a`** and **`b`**: The two schemas, last in the file, so that what is known is at the top however long they are.

Every schema stands on its own: a reference resolves inside the schema or to a meta-schema of draft 2020-12, so a checker needs no other document. Every schema is valid draft 2020-12, which the schema of a case requires.

## What the labels mean

A label holds under these semantics:

- **Draft 2020-12.**
- **`format` is asserted**, not treated as an annotation.
- **Patterns are read as [ECMA-262](https://tc39.es/ecma262/#sec-regexp-regular-expression-objects) regular expressions with the `u` flag**, which is what [the specification recommends](https://json-schema.org/draft/2020-12/json-schema-core#section-6.4). So `\d` and `\w` match ASCII characters only, `.` matches no line terminator, and a character is a code point. A pattern that is not valid with the `u` flag has no meaning, and the corpus claims nothing about a case that uses one.
- **Numbers are doubles.** A question that hinges on digits that a double does not hold is not in the corpus.

## Features

`features` lists what `a` and `b` use between them, sorted by code point. An entry is a keyword of draft 2020-12, or `recursion` where a schema is reached again from itself through a reference.

- **Which keywords.** Those that decide what a schema accepts: the applicator, unevaluated and validation vocabularies, `format`, `$ref` and `$dynamicRef`. `case.schema.json` lists every entry. Left out are the keywords that only name or describe, such as `$id`, `$defs` and `title`, the `content*` keywords, which draft 2020-12 does not assert, and every keyword it does not know.
- **Where a keyword counts.** In the schema itself, in a subschema of a schema that counts, and in the target of a reference in one. A definition that nothing references does not count, and neither does a property that is merely called `format`.
- **Used, not needed.** The list says what is written in the schemas. It does not say that the answer depends on it.

So a checker that treats `format` as an annotation can be measured on the cases that do not list it.

## Scoring

Ask every question whose label is not `null`: `a_subsumes_b`, and `b_subsumes_a` likewise.

- **Wrong** is a yes where the label is `false`, or a no where the label is `true`.
- **Declining to answer is never wrong.** How often a checker declines, and how long it takes, can be measured on every case, including those labelled `null`.
- **A derived label is weaker than upstream's where it is `true`.** A derived `false` is proven by its counterexample. A derived `true` rests on checkers that agree, so a result on upstream's labels alone leaves out the labels that a case names under `derived`.

## Collections

`collections.json` says where the labels of a collection come from:

- **`by-construction`**: The pair was built so that the answer is known.
- **`witness-generator`**: The answer is that of the upstream authors' tool, which is complete but bound by a timeout. Where it gave up, the label is derived or `null`.
- **`upstream-tests`**: The ground truth that the replication package of the jsonsubschema tool gives for its pairs.

The collection `wolflein2026/json-schema-test-suite` is built from the [official JSON Schema Test Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite), where a test case is a schema S with instances that are valid under it or not. The name of a case joins with dots the suite's file, the position of the test case in it, a kind, and for the first two kinds the position of the test: `minimum.0.valid.2` is built from the third test of the first test case of `minimum.json`.

| Kind | `a` | `b` |
| --- | --- | --- |
| `valid` | S | The `const` of one instance |
| `nonvalid` | `not S` | The same `const` |
| `unions` | S | An `anyOf` of the `const` of every valid instance |
| `reflexive` | S | S |
| `universal` | `true` | `anyOf: [S, not S]` |
| `unsatisfiable` | `false` | `allOf: [S, not S]` |

The other collections keep the file names of their source. [How the corpus is built](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/docs/construction.md) says which upstream cases are left out, which labels are corrected and how a label is derived.

## Versions

A corpus has the version of the release it comes with, and the version says what a change means for someone who measures a checker:

- **Major**: A reader has to change, because the layout, the fields of a case, the form of the ids or the semantics of the labels changed.
- **Minor**: Results are no longer comparable, because cases were added or removed, or a label or a schema changed.
- **Patch**: Anything else, such as notes, descriptions, documentation and code.

Results measured on two versions are comparable exactly when their major and minor numbers match. Before 1.0.0, a minor version may also bring what a major version would.

## References

- **`habib2021`**: Andrew Habib, Avraham Shinnar, Martin Hirzel and Michael Pradel. *Finding Data Compatibility Bugs with JSON Subschema Checking*. ISSTA 2021. [doi:10.1145/3460319.3464796](https://doi.org/10.1145/3460319.3464796). `rb-testset` is the pairs of its [replication package](https://zenodo.org/records/4729863); the tool is [IBM/jsonsubschema](https://github.com/IBM/jsonsubschema) (Apache-2.0).
- **`attouche2026`**: Lyes Attouche, Mohamed-Amine Baazizi, Dario Colazzo, Giorgio Ghelli, Carlo Sartiani and Stefanie Scherzinger. *Witness Generation for Classical JSON Schema*. ACM Transactions on Database Systems 51(4), 2026. [doi:10.1145/3799416](https://doi.org/10.1145/3799416). It builds `handwritten-sc` by hand, `mergeallof` from the unit tests of [json-schema-merge-allof](https://github.com/mokkabonna/json-schema-merge-allof) (Martin Hansen), and `schemastore-versions` from the history of [SchemaStore](https://github.com/SchemaStore/schemastore) (Apache-2.0).
- **`baazizi2026`**: Mohamed-Amine Baazizi, Nour El Houda Ben Ali, Dario Colazzo, Giorgio Ghelli, Stefan Klessinger, Carlo Sartiani and Stefanie Scherzinger. *JSON Schema Inclusion through Refutational Normalization: Reconciling Efficiency and Completeness*. [arXiv:2603.25306](https://arxiv.org/abs/2603.25306), 2026. It introduces `oneof-as-anyof`, `additional-as-uneval` and `uneval-as-additional`, built from schemas found on GitHub.
- **`wolflein2026`**: [subsumes-benchmark](https://github.com/georg-wolflein/subsumes-benchmark) builds `json-schema-test-suite` from [json-schema-org/JSON-Schema-Test-Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite) (MIT, Julian Berman). The six kinds of pairs are those of [sdbs-uni-p/json-schema-containment-testsuite](https://github.com/sdbs-uni-p/json-schema-containment-testsuite), described in Lyes Attouche, Mohamed-Amine Baazizi, Dario Colazzo, Yunchen Ding, Michael Fruth, Giorgio Ghelli, Carlo Sartiani and Stefanie Scherzinger. *A Test Suite for JSON Schema Containment*. ER 2021 Demos and Posters, CEUR Workshop Proceedings 2958.

The collections of the first three origins are read from the [artifact of Baazizi et al.](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema), which is GPL-3.0, and are converted to draft 2020-12. The collection built from the test suite is MIT.
