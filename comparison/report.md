# Comparison of inclusion checkers

Corpus `v0.8.0`, all 18,240 tasks, of which 15,052 have a label. Each checker had 10 seconds per task. Run on 2026-11-18 on AMD EPYC 9V45 96-Core Processor (Linux-7.0.0-1019-azure-x86_64-with-glibc2.43).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="chart-dark.svg">
  <img alt="How every task ended, how fast tasks are solved, and the solved share by collection, for each checker" src="chart-light.svg">
</picture>

A task asks whether one schema accepts every instance valid under another. A task is **solved** when the checker answered yes or no and no label of the corpus contradicts the answer. A checker that declines is never wrong; a checker that can only say yes or no is wrong wherever its no meets a label that says yes.

## Outcomes

| Checker | Solved | Correct | Answered, no label | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 50.9% | 6,145 | 3,138 | 8,228 | 533 | 195 | 1 |
| jsoncompat (Rust) | 70.6% | 10,813 | 2,072 | 0 | 0 | 5,352 | 3 |
| jsoncompat (Python) | 70.6% | 10,806 | 2,072 | 0 | 0 | 5,358 | 4 |
| jsonsubschema | 38.8% | 5,731 | 1,341 | 2,351 | 648 | 7,988 | 181 |
| RWG | 84.9% | 12,559 | 2,928 | 503 | 530 | 1,396 | 324 |
| subsumes (Rust) | 94.1% | 14,098 | 3,062 | 11 | 10 | 1,059 | 0 |
| subsumes (Python) | 94.1% | 14,098 | 3,062 | 11 | 10 | 1,059 | 0 |

- **Correct**: the answer is the label.
- **Answered, no label**: the checker answered and the corpus claims nothing.
- **Wrong no**: the checker said no where the label says that A subsumes B.
- **Wrong yes**: the checker said yes where the label says that it does not.
- **No answer**: the checker declined, failed, or cannot read the schemas.
- **Timed out**: no answer within the time.

### With and without `format`

The labels hold with `format` asserted. A checker that treats `format` as an annotation, or does not know it, answers a different question on the tasks that use it, so the same counts follow for the two kinds of task.

The 14,121 tasks whose schemas do not use `format`:

| Checker | Solved | Correct | Answered, no label | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 52.2% | 4,972 | 2,404 | 6,542 | 39 | 163 | 1 |
| jsoncompat (Rust) | 76.9% | 8,828 | 2,032 | 0 | 0 | 3,258 | 3 |
| jsoncompat (Python) | 76.9% | 8,823 | 2,032 | 0 | 0 | 3,262 | 4 |
| jsonsubschema | 43.6% | 4,887 | 1,275 | 1,998 | 137 | 5,732 | 92 |
| RWG | 88.6% | 10,229 | 2,279 | 10 | 37 | 1,391 | 175 |
| subsumes (Rust) | 98.2% | 11,514 | 2,358 | 11 | 10 | 228 | 0 |
| subsumes (Python) | 98.2% | 11,514 | 2,358 | 11 | 10 | 228 | 0 |

The 4,119 tasks whose schemas use `format`:

| Checker | Solved | Correct | Answered, no label | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 46.3% | 1,173 | 734 | 1,686 | 494 | 32 | 0 |
| jsoncompat (Rust) | 49.2% | 1,985 | 40 | 0 | 0 | 2,094 | 0 |
| jsoncompat (Python) | 49.1% | 1,983 | 40 | 0 | 0 | 2,096 | 0 |
| jsonsubschema | 22.1% | 844 | 66 | 353 | 511 | 2,256 | 89 |
| RWG | 72.3% | 2,330 | 649 | 493 | 493 | 5 | 149 |
| subsumes (Rust) | 79.8% | 2,584 | 704 | 0 | 0 | 831 | 0 |
| subsumes (Python) | 79.8% | 2,584 | 704 | 0 | 0 | 831 | 0 |

## Time

| Checker | Solved | Median solved task | Fastest 50% of all tasks within | Fastest 90% of all tasks within | Slowest solved task | Whole run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 50.9% | 454 µs | 19.1 ms | — | 4.4 s | 3 min |
| jsoncompat (Rust) | 70.6% | 277 µs | 607 µs | — | 2.8 s | 6 min |
| jsoncompat (Python) | 70.6% | 426 µs | 961 µs | — | 2.7 s | 7 min |
| jsonsubschema | 38.8% | 7.3 ms | — | — | 8.5 s | 52 min |
| RWG | 84.9% | 871 µs | 1.4 ms | — | 9.8 s | 70 min |
| subsumes (Rust) | 94.1% | 92 µs | 103 µs | 2.1 ms | 949 ms | 3 min |
| subsumes (Python) | 94.1% | 154 µs | 174 µs | 3.6 ms | 1.5 s | 5 min |

The time of a task is measured inside the checker's process, from the two schemas as text to the answer, after 200 unmeasured tasks to warm up. Reading the files, starting the process and rewriting a schema for an older draft are not in it. A share of all tasks that a checker did not reach has no time (—).

## Collections

The share of each collection's tasks that a checker solved.

| Collection | Tasks | Confluent Schema Registry | jsoncompat (Rust) | jsoncompat (Python) | jsonsubschema | RWG | subsumes (Rust) | subsumes (Python) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `additional-as-uneval` | 5,692 | 12.2% | 40.4% | 40.3% | 40.1% | 97.5% | 98.4% | 98.4% |
| `handwritten-sc` | 282 | 51.8% | 35.1% | 35.1% | 49.3% | 99.3% | 100.0% | 100.0% |
| `json-schema-test-suite` | 6,981 | 54.7% | 95.1% | 95.1% | 29.7% | 65.7% | 86.8% | 86.8% |
| `mergeallof` | 174 | 37.4% | 73.0% | 73.0% | 62.6% | 98.9% | 100.0% | 100.0% |
| `oneof-as-anyof` | 1,820 | 98.8% | 56.3% | 56.3% | 17.9% | 93.8% | 97.2% | 97.2% |
| `rb-testset` | 300 | 92.0% | 72.3% | 72.0% | 92.7% | 97.0% | 99.3% | 99.3% |
| `schemastore-versions` | 1,052 | 99.3% | 93.3% | 93.1% | 81.1% | 99.5% | 100.0% | 100.0% |
| `synthesized` | 1,331 | 63.9% | 88.5% | 88.5% | 52.5% | 98.6% | 100.0% | 100.0% |
| `uneval-as-additional` | 608 | 96.7% | 52.8% | 52.6% | 52.0% | 88.3% | 97.7% | 97.7% |

## Where no answer came

| Checker | Declined | Not asked | Failed | Crashed | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 0 | 0 | 195 | 0 | 1 |
| jsoncompat (Rust) | 4,875 | 0 | 471 | 6 | 3 |
| jsoncompat (Python) | 4,881 | 0 | 471 | 6 | 4 |
| jsonsubschema | 0 | 1,780 | 6,208 | 0 | 181 |
| RWG | 0 | 1,241 | 155 | 0 | 324 |
| subsumes (Rust) | 1,059 | 0 | 0 | 0 | 0 |
| subsumes (Python) | 1,059 | 0 | 0 | 0 | 0 |

- **Declined**: the checker ran and said that it does not know.
- **Not asked**: the checker reads an older draft, and that draft cannot express one of the schemas.
- **Failed**: the checker raised an error or rejected a schema.
- **Crashed**: the checker's process died.

## Variants

- jsoncompat (Rust) and jsoncompat (Python) gave the same answer on 18,212 of 18,240 tasks. A timeout or a crash on one side accounts for 1 of the 28 others.
- subsumes (Rust) and subsumes (Python) gave the same answer on 18,240 of 18,240 tasks.

## What ran

| Checker | Version | Reads | Source |
| --- | --- | --- | --- |
| Confluent Schema Registry | 8.4.1 | draft 2020-12 | <https://github.com/confluentinc/schema-registry> |
| jsoncompat (Rust) | 0.6.0 | draft 2020-12 | <https://github.com/ostrowr/jsoncompat> |
| jsoncompat (Python) | 0.6.0 | draft 2020-12 | <https://github.com/ostrowr/jsoncompat> |
| jsonsubschema | 0.0.8 | draft-04 | <https://github.com/IBM/jsonsubschema> |
| RWG | 8064ad8 | draft-07 | <https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema> |
| subsumes (Rust) | 0.2.0 | draft 2020-12 | <https://github.com/georg-wolflein/subsumes> |
| subsumes (Python) | 0.2.0 | draft 2020-12 | <https://github.com/georg-wolflein/subsumes> |

- **Older drafts.** A checker that does not read draft 2020-12 gets every schema rewritten to its draft, with references resolved and keywords renamed. Nothing is encoded by other means: where the older draft lacks a keyword, the checker is not asked.
- **Labels.** Most labels of five collections come from the witness generator that RWG succeeds, so they favour RWG by construction.
- **subsumes.** subsumes is by the author of the corpus and is developed against it, so it does not meet these tasks for the first time as the other checkers do.
- **Duplicates.** `synthesized` largely repeats `json-schema-test-suite`, so the two should not be read as independent evidence.
