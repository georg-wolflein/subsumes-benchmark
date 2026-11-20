# subsumes-benchmark

A benchmark for JSON Schema subsumption checkers: programs that decide whether a schema A accepts every instance that is valid under a schema B. The question is also called schema inclusion or containment. The benchmark is a corpus of pairs of draft 2020-12 schemas with known answers, collected from four works, and a command that runs a checker over it.

## Results

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/comparison/chart-dark.svg">
  <img alt="For each checker, the share of the tasks with a label that it solved within a time" src="https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/comparison/chart-light.svg">
</picture>

<!-- comparison:start -->

| Checker | Version | Solved | Wrong yes | Wrong no | Fastest 50% within | Fastest 90% within |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| [Confluent Schema Registry](https://github.com/confluentinc/schema-registry) | 8.4.1 | 55.9% | 547 | 8,879 | 1.6 ms | — |
| [jsoncompat (Rust)](https://github.com/ostrowr/jsoncompat) | 0.6.0 | 78.5% | 0 | 0 | 365 µs | — |
| [jsoncompat (Python)](https://github.com/ostrowr/jsoncompat) | 0.6.0 | 78.5% | 0 | 0 | 399 µs | — |
| [jsonsubschema](https://github.com/IBM/jsonsubschema) | 0.0.8 | 39.4% | 691 | 2,458 | — | — |
| [RWG](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema) | 8064ad8 | 81.2% | 1,332 | 503 | 958 µs | — |
| [subsumes (Rust)](https://github.com/georg-wolflein/subsumes) | 0.4.0 | 94.2% | 0 | 0 | 87 µs | 2.3 ms |
| [subsumes (Python)](https://github.com/georg-wolflein/subsumes) | 0.4.0 | 94.2% | 0 | 0 | 81 µs | 1.8 ms |

Measured on corpus `v0.9.0`: 24,078 tasks, of which 21,867 have a label, with 10 seconds per task.

<!-- comparison:end -->

A task is one pair of schemas asked in one direction. It is solved when the checker gives the answer that the corpus has, and a wrong yes or a wrong no is an answer that the corpus contradicts. [How a run is measured](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md#how-a-run-is-measured) has the rest.

- **Labels.** Most labels of five collections come from the witness generator that RWG succeeds, so they favour RWG by construction.
- **subsumes.** subsumes is by the author of this benchmark and is developed against it, so it does not meet these tasks for the first time as the other checkers do.

## Collections

<!-- collections:start -->

- **[`habib2021/rb-testset`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/habib2021/rb-testset)**: The pairs of the replication package of the jsonsubschema tool, with schemas from Kubernetes, Snowplow and the Washington Post. From [Habib et al., 2021](https://doi.org/10.1145/3460319.3464796). 292 cases, 562 of 584 tasks with a label.
- **[`attouche2026/handwritten-sc`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/attouche2026/handwritten-sc)**: Hand-written hard cases. From [Attouche et al., 2026](https://doi.org/10.1145/3799416). 138 cases, 276 of 276 tasks with a label.
- **[`attouche2026/mergeallof`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/attouche2026/mergeallof)**: Schemas against the output of a rewriter that merges their allOf, built from the unit tests of json-schema-merge-allof. From [Attouche et al., 2026](https://doi.org/10.1145/3799416). 86 cases, 171 of 172 tasks with a label.
- **[`attouche2026/schemastore-versions`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/attouche2026/schemastore-versions)**: Successive versions of real schemas from SchemaStore. From [Attouche et al., 2026](https://doi.org/10.1145/3799416). 469 cases, 613 of 938 tasks with a label.
- **[`baazizi2026/oneof-as-anyof`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/baazizi2026/oneof-as-anyof)**: Real schemas against themselves with oneOf replaced by anyOf: is oneOf used where anyOf would be equivalent? From [Baazizi et al., 2026](https://arxiv.org/abs/2603.25306). 904 cases, 734 of 1,808 tasks with a label.
- **[`baazizi2026/additional-as-uneval`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/baazizi2026/additional-as-uneval)**: Real schemas against themselves with additionalProperties and items rewritten through unevaluatedProperties and unevaluatedItems. From [Baazizi et al., 2026](https://arxiv.org/abs/2603.25306). 2,817 cases, 5,455 of 5,634 tasks with a label.
- **[`baazizi2026/uneval-as-additional`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/baazizi2026/uneval-as-additional)**: Schemas using unevaluatedProperties or unevaluatedItems against a translation to additionalProperties and items. From [Baazizi et al., 2026](https://arxiv.org/abs/2603.25306). 297 cases, 268 of 594 tasks with a label.
- **[`wolflein2026/json-schema-test-suite`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/corpus/wolflein2026/json-schema-test-suite)**: Pairs built from the test cases of the official JSON Schema Test Suite for draft 2020-12: each schema against its instances, its negation and itself. From [This repository](https://github.com/georg-wolflein/subsumes-benchmark). 5,740 cases, 11,353 of 11,480 tasks with a label.

In all: 10,743 cases, 19,432 of 21,486 tasks with a label.

<!-- collections:end -->

A collection lies in the folder of the work that first published its pairs, and a case is one JSON file in it. [The page of the corpus](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/corpus/README.md) describes a case and says what its labels mean.

## Use

The command needs Python 3.14, which [uv](https://docs.astral.sh/uv/) fetches by itself. To get the latest corpus:

```bash
uvx subsumes-benchmark corpus corpus   # unpacks into corpus/
```

The same corpus is a file of every [release](https://github.com/georg-wolflein/subsumes-benchmark/releases), for whoever has no Python at hand:

```bash
curl -fsSLO https://github.com/georg-wolflein/subsumes-benchmark/releases/latest/download/corpus.tar.zst
zstd -dc corpus.tar.zst | tar -xf -   # unpacks into corpus/
```

To run a checker over it:

```bash
uvx subsumes-benchmark run path/to/checker   # writes results/<folder of the checker>/
```

A checker is a folder with a `checker.json` and an adapter, a program that answers one question per line. [The page of the checkers](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md) says how to write one.

The package of a version holds the corpus of that version, so `uvx subsumes-benchmark==<version>` pins both. Results measured on two versions are comparable exactly when their major and minor numbers match.

## Documentation

- **[The corpus](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/corpus/README.md)**: its layout, what a case holds, what the labels mean and how to score a checker with them.
- **[How the corpus is built](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/docs/construction.md)**: the pairs built from the test suite, the cases left out, the labels corrected and the labels derived.
- **[The checkers](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md)**: running a checker, how a run is measured, and writing an adapter.
- **[Contributing](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/CONTRIBUTING.md)**: rebuilding the corpus, the checks, and how a pull request decides the next version.

## Licence

The code is MIT licensed, except [`checkers/rwg/`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/checkers/rwg), which is compiled together with RWG and is GPL-3.0 like it. The corpus keeps the licences of its sources: GPL-3.0 for the collections read from the artifact of Baazizi et al., and MIT for the one built from the official JSON Schema Test Suite. The folder of each collection holds the text as `LICENSE`. The package on PyPI holds the code and the corpus, so it is licensed `MIT AND GPL-3.0-only`.
