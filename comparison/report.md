# Comparison of inclusion checkers

Corpus `v0.9.0`, all 24,078 tasks, of which 21,867 have a label. Each checker had 10 seconds per task. Run on 2026-11-18 on AMD EPYC 9V74 80-Core Processor (Linux-7.0.0-1019-azure-x86_64-with-glibc2.43).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="chart-dark.svg">
  <img alt="How every task ended, how fast tasks are solved, and the solved share by collection, for each checker" src="chart-light.svg">
</picture>

A task asks whether one schema accepts every instance valid under another. Every case is two tasks, one in each direction, and the corpus has a label for some of them. A task is **solved** when the checker gave the answer that the label gives, so only a task with a label can be solved, and every share of solved tasks is a share of the tasks with a label. A checker that declines is never wrong; a checker that can only say yes or no is wrong wherever its no meets a label that says yes.

## Outcomes

The 21,867 tasks with a label:

| Checker | Solved | Correct | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 55.9% | 12,229 | 8,879 | 547 | 201 | 11 |
| jsoncompat (Rust) | 78.5% | 17,170 | 0 | 0 | 4,697 | 0 |
| jsoncompat (Python) | 78.5% | 17,169 | 0 | 0 | 4,698 | 0 |
| jsonsubschema | 39.4% | 8,626 | 2,458 | 691 | 9,961 | 131 |
| RWG | 81.2% | 17,754 | 503 | 1,332 | 2,163 | 115 |
| subsumes (Rust) | 94.2% | 20,594 | 0 | 0 | 1,273 | 0 |
| subsumes (Python) | 94.2% | 20,594 | 0 | 0 | 1,273 | 0 |

- **Correct**: the answer is the label.
- **Wrong no**: the checker said no where the label says that A subsumes B, or gave a counterexample with its no that is none; see [below](#counterexamples).
- **Wrong yes**: the checker said yes where the label says that it does not.
- **No answer**: the checker declined, failed, or cannot read the schemas.
- **Timed out**: no answer within the time.

### Without a label

The 2,211 tasks without a label. An answer to one can be held against nothing, so it is counted and not scored: a checker that always answers has answered them all. What can be held against something is a counterexample, and a no with one that is none is a wrong no here too.

| Checker | Answered | Yes | No | Wrong no | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 97.8% | 1,151 | 1,011 | 0 | 48 | 1 |
| jsoncompat (Rust) | 47.7% | 1,047 | 8 | 0 | 1,152 | 4 |
| jsoncompat (Python) | 47.9% | 1,047 | 12 | 0 | 1,149 | 3 |
| jsonsubschema | 32.1% | 624 | 85 | 0 | 1,430 | 72 |
| RWG | 88.9% | 1,945 | 21 | 0 | 12 | 233 |
| subsumes (Rust) | 89.0% | 1,951 | 16 | 0 | 244 | 0 |
| subsumes (Python) | 89.0% | 1,951 | 16 | 0 | 244 | 0 |

### With and without `format`

The labels hold with `format` asserted. A checker that treats `format` as an annotation, or does not know it, answers a different question on the tasks that use it, so the counts of the tasks with a label follow for the two kinds of task.

The 16,740 whose schemas do not use `format`:

| Checker | Solved | Correct | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 55.5% | 9,285 | 7,193 | 52 | 199 | 11 |
| jsoncompat (Rust) | 80.4% | 13,463 | 0 | 0 | 3,277 | 0 |
| jsoncompat (Python) | 80.4% | 13,463 | 0 | 0 | 3,277 | 0 |
| jsonsubschema | 41.2% | 6,893 | 2,105 | 180 | 7,479 | 83 |
| RWG | 86.4% | 14,466 | 10 | 41 | 2,155 | 68 |
| subsumes (Rust) | 98.8% | 16,532 | 0 | 0 | 208 | 0 |
| subsumes (Python) | 98.8% | 16,532 | 0 | 0 | 208 | 0 |

The 5,127 whose schemas use `format`:

| Checker | Solved | Correct | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 57.4% | 2,944 | 1,686 | 495 | 2 | 0 |
| jsoncompat (Rust) | 72.3% | 3,707 | 0 | 0 | 1,420 | 0 |
| jsoncompat (Python) | 72.3% | 3,706 | 0 | 0 | 1,421 | 0 |
| jsonsubschema | 33.8% | 1,733 | 353 | 511 | 2,482 | 48 |
| RWG | 64.1% | 3,288 | 493 | 1,291 | 8 | 47 |
| subsumes (Rust) | 79.2% | 4,062 | 0 | 0 | 1,065 | 0 |
| subsumes (Python) | 79.2% | 4,062 | 0 | 0 | 1,065 | 0 |

### Labels of upstream and derived labels

A label is upstream's, or it is derived where upstream gives none: `false` from a counterexample, which proves it, and `true` from checkers that agree, which does not. A checker whose answers the labels are derived from is measured against itself on those, so the counts of the tasks with a label follow for the two kinds of label.

The 14,938 whose label is upstream's:

| Checker | Solved | Correct | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 40.6% | 6,065 | 8,194 | 533 | 137 | 9 |
| jsoncompat (Rust) | 71.7% | 10,714 | 0 | 0 | 4,224 | 0 |
| jsoncompat (Python) | 71.7% | 10,712 | 0 | 0 | 4,226 | 0 |
| jsonsubschema | 37.7% | 5,627 | 2,337 | 646 | 6,210 | 118 |
| RWG | 83.3% | 12,445 | 503 | 530 | 1,390 | 70 |
| subsumes (Rust) | 93.8% | 14,014 | 0 | 0 | 924 | 0 |
| subsumes (Python) | 93.8% | 14,014 | 0 | 0 | 924 | 0 |

The 6,929 whose label is derived:

| Checker | Solved | Correct | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 89.0% | 6,164 | 685 | 14 | 64 | 2 |
| jsoncompat (Rust) | 93.2% | 6,456 | 0 | 0 | 473 | 0 |
| jsoncompat (Python) | 93.2% | 6,457 | 0 | 0 | 472 | 0 |
| jsonsubschema | 43.3% | 2,999 | 121 | 45 | 3,751 | 13 |
| RWG | 76.6% | 5,309 | 0 | 802 | 773 | 45 |
| subsumes (Rust) | 95.0% | 6,580 | 0 | 0 | 349 | 0 |
| subsumes (Python) | 95.0% | 6,580 | 0 | 0 | 349 | 0 |

## Time

| Checker | Solved | Median solved task | Fastest 50% within | Fastest 90% within | Slowest solved task | Whole run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 55.9% | 571 µs | 1.6 ms | — | 9.7 s | 5 min |
| jsoncompat (Rust) | 78.5% | 239 µs | 365 µs | — | 3.8 s | 7 min |
| jsoncompat (Python) | 78.5% | 271 µs | 399 µs | — | 2.3 s | 6 min |
| jsonsubschema | 39.4% | 6.0 ms | — | — | 9.9 s | 65 min |
| RWG | 81.2% | 601 µs | 958 µs | — | 9.9 s | 73 min |
| subsumes (Rust) | 94.2% | 77 µs | 87 µs | 2.3 ms | 1.4 s | 4 min |
| subsumes (Python) | 94.2% | 73 µs | 81 µs | 1.8 ms | 858 ms | 3 min |

The time of a task is measured inside the checker's process, from the two schemas as text to the answer, after 200 unmeasured tasks to warm up. Reading the files, starting the process and rewriting a schema for an older draft are not in it. The fastest 50% is the time within which a checker solved half of the tasks with a label; a share that it did not reach has no time (—).

## Collections

The share of each collection's tasks with a label that a checker solved.

| Collection | With a label | Confluent Schema Registry | jsoncompat (Rust) | jsoncompat (Python) | jsonsubschema | RWG | subsumes (Rust) | subsumes (Python) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `additional-as-uneval` | 5,455 | 8.9% | 40.5% | 40.5% | 40.4% | 99.4% | 99.7% | 99.7% |
| `handwritten-sc` | 276 | 52.2% | 33.7% | 33.7% | 48.6% | 99.3% | 100.0% | 100.0% |
| `json-schema-test-suite` | 11,353 | 70.6% | 94.8% | 94.8% | 32.8% | 65.4% | 89.1% | 89.1% |
| `mergeallof` | 171 | 37.4% | 73.1% | 73.1% | 63.2% | 98.8% | 100.0% | 100.0% |
| `oneof-as-anyof` | 734 | 72.3% | 83.4% | 83.5% | 28.1% | 95.8% | 99.0% | 99.0% |
| `rb-testset` | 562 | 92.9% | 74.7% | 74.7% | 92.2% | 97.0% | 99.6% | 99.6% |
| `schemastore-versions` | 613 | 98.2% | 89.6% | 89.4% | 83.7% | 99.3% | 100.0% | 100.0% |
| `synthesized` | 2,435 | 67.6% | 91.2% | 91.2% | 46.5% | 97.4% | 100.0% | 100.0% |
| `uneval-as-additional` | 268 | 82.5% | 67.5% | 67.5% | 32.8% | 86.2% | 95.1% | 95.1% |

## Counterexamples

A checker may give a counterexample with a no: an instance that is valid under B and invalid under A. A validator is asked about each one, [jsonschema-rs](https://github.com/Stranger6667/jsonschema) for draft 2020-12 with `format` asserted, and about the schemas as the corpus has them, whatever draft the checker reads. A no with a counterexample that is none counts as a wrong no, with a label or without.

| Checker | Said no | With a counterexample | Confirmed | No instance of B | Accepted by A | Not checked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 17,915 | 0 | 0 | 0 | 0 | 0 |
| jsoncompat (Rust) | 7,890 | 0 | 0 | 0 | 0 | 0 |
| jsoncompat (Python) | 7,893 | 0 | 0 | 0 | 0 | 0 |
| jsonsubschema | 5,557 | 0 | 0 | 0 | 0 | 0 |
| RWG | 6,647 | 0 | 0 | 0 | 0 | 0 |
| subsumes (Rust) | 7,880 | 7,880 | 7,872 | 0 | 0 | 8 |
| subsumes (Python) | 7,880 | 7,880 | 7,872 | 0 | 0 | 8 |

- **Confirmed**: B accepts the counterexample and A rejects it.
- **No instance of B**: B rejects it, so A did not have to accept it.
- **Accepted by A**: A accepts it, so it tells the two schemas apart in nothing.
- **Not checked**: the validator does not take one of the two schemas.

## Where no answer came

Among all tasks, with a label and without:

| Checker | Declined | Not asked | Failed | Crashed | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 0 | 0 | 249 | 0 | 12 |
| jsoncompat (Rust) | 5,361 | 0 | 482 | 6 | 4 |
| jsoncompat (Python) | 5,359 | 0 | 482 | 6 | 3 |
| jsonsubschema | 0 | 2,548 | 8,843 | 0 | 203 |
| RWG | 0 | 1,838 | 337 | 0 | 348 |
| subsumes (Rust) | 1,517 | 0 | 0 | 0 | 0 |
| subsumes (Python) | 1,517 | 0 | 0 | 0 | 0 |

- **Declined**: the checker ran and said that it does not know.
- **Not asked**: the checker reads an older draft, and that draft cannot express one of the schemas.
- **Failed**: the checker raised an error or rejected a schema.
- **Crashed**: the checker's process died.

## Variants

- jsoncompat (Rust) and jsoncompat (Python) gave the same answer on 24,060 of 24,078 tasks. A timeout or a crash on one side accounts for 1 of the 18 others.
- subsumes (Rust) and subsumes (Python) gave the same answer on 24,078 of 24,078 tasks.

## What ran

| Checker | Version | Reads | Source |
| --- | --- | --- | --- |
| Confluent Schema Registry | 8.4.1 | draft 2020-12 | <https://github.com/confluentinc/schema-registry> |
| jsoncompat (Rust) | 0.6.0 | draft 2020-12 | <https://github.com/ostrowr/jsoncompat> |
| jsoncompat (Python) | 0.6.0 | draft 2020-12 | <https://github.com/ostrowr/jsoncompat> |
| jsonsubschema | 0.0.8 | draft-04 | <https://github.com/IBM/jsonsubschema> |
| RWG | 8064ad8 | draft-07 | <https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema> |
| subsumes (Rust) | 0.4.0 | draft 2020-12 | <https://github.com/georg-wolflein/subsumes> |
| subsumes (Python) | 0.4.0 | draft 2020-12 | <https://github.com/georg-wolflein/subsumes> |

- **Older drafts.** A checker that does not read draft 2020-12 gets every schema rewritten to its draft, with references resolved and keywords renamed. Nothing is encoded by other means: where the older draft lacks a keyword, the checker is not asked.
- **Labels.** Most labels of five collections come from the witness generator that RWG succeeds, so they favour RWG by construction.
- **subsumes.** subsumes is by the author of the corpus and is developed against it, so it does not meet these tasks for the first time as the other checkers do.
- **Duplicates.** `synthesized` largely repeats `json-schema-test-suite`, so the two should not be read as independent evidence.
