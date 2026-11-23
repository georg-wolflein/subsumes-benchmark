# JSON schema subsumption benchmark

A benchmark for JSON Schema subsumption checkers: programs that decide whether a schema _A_ accepts every instance that is valid under a schema _B_.
This problem is also known as schema _inclusion_ or _containment_.
The benchmark is a corpus of **<!-- num_labelled_tasks:start -->19,432<!-- num_labelled_tasks:end -->** pairs of [draft 2020-12](https://json-schema.org/draft/2020-12) schemas with known answers, collected from four works.

## Results

Each task asks whether schema _A_ subsumes schema _B_. A checker can:

- Answer **yes**: _A_ accepts everything that _B_ accepts.
- Answer **no**: at least one instance is accepted by _B_ but rejected by _A_. Some checkers provide such an instance as a counterexample.
- **Decline to answer**: the checker cannot decide, for example because it reaches a resource limit.

Reference answers come from the source collections or are known by construction. Where an answer is missing, we establish **no** by validating a checker-generated counterexample against both schemas, or infer **yes** when at least two checkers agree and none disagrees, excluding schemas with patterns or formats. These inferred yes answers rest on consensus rather than proof.

The plot and results table below show the proportion of tasks solved within a given time, with one curve per checker. See [How a run is measured](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md#how-a-run-is-measured) for details.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/comparison/chart-dark.svg">
  <img alt="For each checker, the share of the tasks with a label that it solved within a time" src="https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/comparison/chart-light.svg">
</picture>

<details>
<summary>Results table</summary>

<!-- comparison:start -->

| Checker | Version | Correct results | Incorrect results | Fastest 50% within | Fastest 90% within |
| --- | ---: | ---: | ---: | ---: | ---: |
| [subsumes (Rust)](https://github.com/georg-wolflein/subsumes) | 0.5.0 | **93.5%** | **0.0%** | **105 µs** | **2.6 ms** |
| [subsumes (Python)](https://github.com/georg-wolflein/subsumes) | 0.5.0 | **93.5%** | **0.0%** | 140 µs | 3.0 ms |
| [RWG](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema) | 8064ad8 | 79.2% | 9.4% | 1.3 ms | — |
| [jsoncompat (Rust)](https://github.com/ostrowr/jsoncompat) | 0.6.0 | 76.9% | **0.0%** | 324 µs | — |
| [jsoncompat (Python)](https://github.com/ostrowr/jsoncompat) | 0.6.0 | 76.9% | **0.0%** | 415 µs | — |
| [Confluent Schema Registry](https://github.com/confluentinc/schema-registry) | 8.4.1 | 54.5% | 44.4% | 1.6 ms | — |
| [jsonsubschema](https://github.com/IBM/jsonsubschema) | 0.0.8 | 38.7% | 15.7% | — | — |

<!-- comparison:end -->

</details>

The results were measured on <!-- version:start -->[`v0.10.2`](https://github.com/georg-wolflein/subsumes-benchmark/releases/tag/v0.10.2)<!-- version:end --> of the corpus.

## Collections

The benchmark brings together <!-- num_collections:start -->8<!-- num_collections:end --> collections of tasks from the sources listed below (see the [corpus documentation](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/corpus/README.md) for more information):

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

## Use

To get the latest corpus (requires [`uv`](https://docs.astral.sh/uv/)):

```bash
uvx subsumes-benchmark corpus ./corpus   # unpacks into corpus/
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

A checker is a folder with a `checker.json` and an adapter (a program that answers one question per line). The [documentation](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md) describes how to create one yourself.

## Documentation

- **[The corpus](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/corpus/README.md)**: its layout, what a case holds, what the labels mean and how to score a checker with them.
- **[How the corpus is built](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/docs/construction.md)**: the pairs built from the test suite, the cases left out, the labels corrected and the labels derived.
- **[The checkers](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md)**: running a checker, how a run is measured, and writing an adapter.
- **[Contributing](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/CONTRIBUTING.md)**: rebuilding the corpus, the checks, and how a pull request decides the next version.

## Licence

The code is MIT licensed, except [`checkers/rwg/`](https://github.com/georg-wolflein/subsumes-benchmark/tree/main/checkers/rwg), which is compiled together with RWG and is GPL-3.0 like it. The corpus keeps the licences of its sources: GPL-3.0 for the collections read from the artifact of Baazizi et al., and MIT for the one built from the official JSON Schema Test Suite. The folder of each collection holds the text as `LICENSE`. The package on PyPI holds the code and the corpus, so it is licensed `MIT AND GPL-3.0-only`.
