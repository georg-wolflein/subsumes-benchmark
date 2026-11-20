# Checkers

A checker is a program that says whether a schema `a` accepts every instance valid under a schema `b`. Each folder here makes one checker answer the tasks of the corpus, so that one command runs them all the same way.

| Folder | Checker | Used through | Reads |
| --- | --- | --- | --- |
| `confluent/` | The JSON Schema compatibility check of [Confluent Schema Registry](https://github.com/confluentinc/schema-registry) | `kafka-json-schema-provider` from Confluent's Maven repository | draft 2020-12 |
| `jsoncompat/` | [jsoncompat](https://github.com/ostrowr/jsoncompat) | the crate from crates.io | draft 2020-12 |
| `jsoncompat-python/` | jsoncompat | the package from PyPI | draft 2020-12 |
| `jsonsubschema/` | [jsonsubschema](https://github.com/IBM/jsonsubschema) | the package from PyPI | draft-04 |
| `rwg/` | [RWG](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema), the tool of *JSON Schema Inclusion through Refutational Normalization* | its sources, in the submodule `sources/inclusion-artifact` | draft-07 |
| `subsumes/` | [subsumes](https://github.com/georg-wolflein/subsumes) | the crate from crates.io | draft 2020-12 |
| `subsumes-python/` | subsumes | the package from PyPI | draft 2020-12 |

A checker is taken from a package index wherever it is published to one, at a pinned version.

## Run a checker

The command is the package [`subsumes-benchmark`](https://pypi.org/project/subsumes-benchmark/), which holds the corpus of its version. In a checkout, `uv run subsumes-benchmark` runs the same command over `corpus/`.

```bash
# Unpack the corpus into corpus/.
uvx subsumes-benchmark corpus corpus
# Run a checker over every task; --limit 300 runs a sample.
uvx subsumes-benchmark run path/to/checker
# Hold the run against an earlier one, as a comment for a pull request.
uvx subsumes-benchmark diff results/checker --base base/checker
# Plot how fast the checkers under results/ are, and write their results as a table.
uvx --from 'subsumes-benchmark[report]' subsumes-benchmark report results
```

- **`run`** takes the folder of a checker, which can be anywhere, and writes a run to `results/<name of the folder>/`: `results.jsonl` with one line per task and `run.json` with what ran, as [`result.schema.json`](../schemas/result.schema.json) and [`run.schema.json`](../schemas/run.schema.json) describe them.
- **`diff`** lists the answers by collection with what changed, the wrong answers, and the tasks that the base answered and the change does not. It fails when an answer is wrong, when a task ended in an error, a crash or a timeout, and when a task of the base is no longer answered, unless `--allow-lost` accepts that.
- **`report`** writes four files to `comparison/`, or to the folder that `--out` names: the plot for light and for dark pages, the table as `results.md`, which it prints too, and the version of the corpus as `version.md`. The table lists the run that solved most first and has the best value of every column in bold, and the plot has one curve per checker, that of the variant that solved most.

The `Comparison` workflow runs every checker here over every task after each release, and opens a pull request with the plot and the table. It also puts the table and the version of the corpus into the main README.

## How a run is measured

- **A task** is one question of the corpus, and every case is two: whether A subsumes B, and whether B subsumes A.
- **Solved** is a task where the checker gave the answer that the label gives. Only a task with a label can be solved, and the share of solved tasks is a share of those. The table calls it a correct result.
- **Wrong** is an answer that the label contradicts. A no with a counterexample that is none is wrong too, with a label or without: the runner asks [jsonschema-rs](https://github.com/Stranger6667/jsonschema), with `format` asserted, whether the instance is valid under `b` and invalid under `a`. The table calls it an incorrect result, and gives the wrong answers as a share of the tasks with a label too.
- **Time** is measured inside the checker's process, from the two schemas as text to the answer. A checker runs alone on its machine, as one process that answers 200 tasks before anything is measured.
- **A timeout** is 10 seconds per task unless `--timeout` says otherwise. The runner waits two seconds longer, then kills the adapter and starts it again.
- **An older draft** is what a checker gets that does not read draft 2020-12: the runner rewrites every schema to its `dialect`, with references resolved and keywords renamed. Where the older draft cannot express a schema, the checker is not asked and the task counts as `unsupported`.

## Write an adapter

A checker's folder holds a `checker.json`, which [`checker.schema.json`](../schemas/checker.schema.json) describes key by key, and the adapter it names:

```json
{
  "$schema": "../../schemas/checker.schema.json",
  "label": "jsoncompat",
  "variant": "Rust",
  "version": "0.6.0",
  "homepage": "https://github.com/ostrowr/jsoncompat",
  "dialect": "2020-12",
  "build": ["cargo", "build", "--release", "--locked"],
  "run": ["target/release/adapter"]
}
```

Folders with the same `label` are variants of one checker. In another repository, `$schema` is `https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/schemas/checker.schema.json`.

The adapter starts once and answers many requests, so that starting it is not part of any measured time. It reads its standard input and writes its standard output, one JSON document per line: first that it is ready, then one reply for every request.

```json
{"ready": true}
{"a": {"type": "string"}, "b": {"maxLength": 3}, "timeout": 10.0}
{"answer": true, "seconds": 0.00042}
{"answer": false, "seconds": 0.00042, "counterexample": "x"}
{"answer": null, "seconds": 0.00042, "reason": "uniqueItems", "message": "#/uniqueItems in schema A is not supported"}
{"failure": "error", "message": "the schema is no schema"}
{"failure": "timeout"}
```

| Reply | When | Has to have | May have |
| --- | --- | --- | --- |
| `"answer": true` | `a` accepts every instance of `b` | `seconds` | |
| `"answer": false` | It does not | `seconds` | `counterexample`, `message` |
| `"answer": null` | The checker ran and declined | `seconds` | `reason`, `message` |
| `"failure": "error"` | The checker failed, or rejected a schema | `message` | `seconds` |
| `"failure": "timeout"` | The checker stopped itself after the time allowed | | |

The schemas [`ready`](../schemas/ready.schema.json), [`request`](../schemas/request.schema.json) and [`reply`](../schemas/reply.schema.json) say what each key means, and the runner reads a line with models generated from them.

- **`seconds`** covers parsing each schema once and the check, which is what someone pays who holds two schemas as text. An adapter whose checker takes a parsed schema starts the clock before it parses the request, since that parses the two. An adapter whose checker takes text writes each schema back to text first, and starts the clock then.
- **Nothing but replies on the standard output.** The runner keeps the standard error as a log next to the results.
- **Only the keys of the reply, and no `null` for a key that does not apply.** A line that is no reply by the schema counts as a crash of the adapter.
- **Assert `format`** where the checker can, since the labels hold with `format` asserted.
- **Survive an error.** Catch what the checker throws and reply with the failure `error`, so that the next request is answered by a warm process.

To add a checker here: create the folder, pin the checker's version and commit a lock file where the toolchain has one, try it with `uv run subsumes-benchmark run checkers/<folder> --limit 300`, and add the folder to the matrix in `.github/workflows/comparison.yml` and to the table above.

## Licence

The adapters are MIT licensed like the rest of this repository, with one exception: **`rwg/` is licensed under GPL-3.0**, because it is compiled together with RWG, which is. [`rwg/LICENSE`](rwg/LICENSE) has the text. Nothing else in the repository links to RWG; the runner talks to every adapter as a separate process.
