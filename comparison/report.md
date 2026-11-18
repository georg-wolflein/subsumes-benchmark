# Comparison of inclusion checkers

Corpus `v0.5.0`, all 18,262 tasks, of which 15,094 have a label. Each checker had 10 seconds per task. Run on 2026-11-17 on AMD EPYC 9V74 80-Core Processor (Linux-7.0.0-1019-azure-x86_64-with-glibc2.43).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="chart-dark.svg">
  <img alt="How every task ended, how fast tasks are solved, and the solved share by collection, for each checker" src="chart-light.svg">
</picture>

A task asks whether one schema accepts every instance valid under another. A task is **solved** when the checker answered yes or no and no label of the corpus contradicts the answer. A checker that declines is never wrong; a checker that can only say yes or no is wrong wherever its no meets a label that says yes.

## Outcomes

| Checker | Solved | Correct | Answered, no label | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 50.7% | 6,155 | 3,105 | 8,267 | 533 | 201 | 1 |
| jsoncompat (Rust) | 70.5% | 10,803 | 2,069 | 11 | 12 | 5,363 | 4 |
| jsoncompat (Python) | 70.5% | 10,802 | 2,069 | 11 | 12 | 5,364 | 4 |
| jsonsubschema | 38.9% | 5,769 | 1,335 | 2,348 | 641 | 7,981 | 188 |
| RWG | 84.8% | 12,590 | 2,904 | 507 | 537 | 1,400 | 324 |

- **Correct**: the answer is the label.
- **Answered, no label**: the checker answered and the corpus claims nothing.
- **Wrong no**: the checker said no where the label says that A subsumes B.
- **Wrong yes**: the checker said yes where the label says that it does not.
- **No answer**: the checker declined, failed, or cannot read the schemas.
- **Timed out**: no answer within the time.

### With and without `format`

The labels hold with `format` asserted. A checker that treats `format` as an annotation, or does not know it, answers a different question on the tasks that use it, so the same counts follow for the two kinds of task.

The 14,141 tasks whose schemas do not use `format`:

| Checker | Solved | Correct | Answered, no label | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 52.1% | 4,985 | 2,384 | 6,563 | 39 | 169 | 1 |
| jsoncompat (Rust) | 76.7% | 8,818 | 2,028 | 11 | 12 | 3,268 | 4 |
| jsoncompat (Python) | 76.7% | 8,818 | 2,028 | 11 | 12 | 3,268 | 4 |
| jsonsubschema | 43.8% | 4,924 | 1,269 | 1,994 | 130 | 5,727 | 97 |
| RWG | 88.5% | 10,241 | 2,272 | 14 | 44 | 1,395 | 175 |

The 4,121 tasks whose schemas use `format`:

| Checker | Solved | Correct | Answered, no label | Wrong no | Wrong yes | No answer | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 45.9% | 1,170 | 721 | 1,704 | 494 | 32 | 0 |
| jsoncompat (Rust) | 49.2% | 1,985 | 41 | 0 | 0 | 2,095 | 0 |
| jsoncompat (Python) | 49.1% | 1,984 | 41 | 0 | 0 | 2,096 | 0 |
| jsonsubschema | 22.1% | 845 | 66 | 354 | 511 | 2,254 | 91 |
| RWG | 72.3% | 2,349 | 632 | 493 | 493 | 5 | 149 |

## Time

| Checker | Solved | Median solved task | Fastest 50% of all tasks within | Fastest 90% of all tasks within | Slowest solved task | Whole run |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 50.7% | 557 µs | 31.3 ms | — | 6.7 s | 3 min |
| jsoncompat (Rust) | 70.5% | 271 µs | 606 µs | — | 2.7 s | 5 min |
| jsoncompat (Python) | 70.5% | 399 µs | 930 µs | — | 2.6 s | 6 min |
| jsonsubschema | 38.9% | 9.4 ms | — | — | 9.7 s | 57 min |
| RWG | 84.8% | 838 µs | 1.3 ms | — | 9.9 s | 70 min |

The time of a task is measured inside the checker's process, from the two schemas as text to the answer, after 200 unmeasured tasks to warm up. Reading the files, starting the process and rewriting a schema for an older draft are not in it. A share of all tasks that a checker did not reach has no time (—).

## Collections

The share of each collection's tasks that a checker solved.

| Collection | Tasks | Confluent Schema Registry | jsoncompat (Rust) | jsoncompat (Python) | jsonsubschema | RWG |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `additional-as-uneval` | 5,694 | 11.6% | 40.4% | 40.3% | 40.0% | 97.5% |
| `handwritten-sc` | 282 | 51.8% | 35.1% | 35.1% | 49.3% | 99.3% |
| `json-schema-test-suite` | 6,995 | 54.8% | 94.8% | 94.8% | 30.1% | 65.6% |
| `mergeallof` | 174 | 37.4% | 73.0% | 73.0% | 62.6% | 98.9% |
| `oneof-as-anyof` | 1,822 | 98.7% | 56.3% | 56.3% | 18.0% | 93.8% |
| `rb-testset` | 300 | 92.0% | 72.3% | 72.0% | 92.7% | 97.0% |
| `schemastore-versions` | 1,056 | 99.0% | 92.5% | 92.9% | 80.7% | 99.5% |
| `synthesized` | 1,331 | 63.9% | 88.5% | 88.5% | 52.5% | 98.6% |
| `uneval-as-additional` | 608 | 96.7% | 52.6% | 52.6% | 52.0% | 88.3% |

## Where no answer came

| Checker | Declined | Not asked | Failed | Crashed | Timed out |
| --- | ---: | ---: | ---: | ---: | ---: |
| Confluent Schema Registry | 0 | 0 | 201 | 0 | 1 |
| jsoncompat (Rust) | 4,878 | 0 | 479 | 6 | 4 |
| jsoncompat (Python) | 4,879 | 0 | 479 | 6 | 4 |
| jsonsubschema | 0 | 1,780 | 6,201 | 0 | 188 |
| RWG | 0 | 1,241 | 159 | 0 | 324 |

- **Declined**: the checker ran and said that it does not know.
- **Not asked**: the checker reads an older draft, and that draft cannot express one of the schemas.
- **Failed**: the checker raised an error or rejected a schema.
- **Crashed**: the checker's process died.

## Variants

- jsoncompat (Rust) and jsoncompat (Python) gave the same answer on 18,245 of 18,262 tasks. A timeout or a crash on one side accounts for 0 of the 17 others.

## What ran

| Checker | Version | Reads | Source |
| --- | --- | --- | --- |
| Confluent Schema Registry | 8.4.1 | draft 2020-12 | <https://github.com/confluentinc/schema-registry> |
| jsoncompat (Rust) | 0.6.0 | draft 2020-12 | <https://github.com/ostrowr/jsoncompat> |
| jsoncompat (Python) | 0.6.0 | draft 2020-12 | <https://github.com/ostrowr/jsoncompat> |
| jsonsubschema | 0.0.8 | draft-04 | <https://github.com/IBM/jsonsubschema> |
| RWG | 8064ad8 | draft-07 | <https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema> |

- **Older drafts.** A checker that does not read draft 2020-12 gets every schema rewritten to its draft, with references resolved and keywords renamed. Nothing is encoded by other means: where the older draft lacks a keyword, the checker is not asked.
- **Labels.** Most labels of five collections come from the witness generator that RWG succeeds, so they favour RWG by construction.
- **subsumes.** subsumes is by the author of the corpus and is developed against it, so it does not meet these tasks for the first time as the other checkers do.
- **Duplicates.** `synthesized` largely repeats `json-schema-test-suite`, so the two should not be read as independent evidence.
