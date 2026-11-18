# Checkers

Each folder here makes one inclusion checker answer the tasks of the corpus, so that `subsumes-benchmark run` can run them all the same way. The [README](../README.md#comparing-checkers) says how to run a comparison and where its report goes.

| Folder | Checker | Used through | Reads |
| --- | --- | --- | --- |
| `confluent/` | The JSON Schema compatibility check of [Confluent Schema Registry](https://github.com/confluentinc/schema-registry) | `kafka-json-schema-provider` from Confluent's Maven repository | draft 2020-12 |
| `jsoncompat/` | [jsoncompat](https://github.com/ostrowr/jsoncompat) | the crate from crates.io | draft 2020-12 |
| `jsoncompat-python/` | jsoncompat | the package from PyPI | draft 2020-12 |
| `jsonsubschema/` | [jsonsubschema](https://github.com/IBM/jsonsubschema) | the package from PyPI | draft-04 |
| `rwg/` | [RWG](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema), the tool of *JSON Schema Inclusion through Refutational Normalization* | its sources, in the submodule `sources/inclusion-artifact` | draft-07 |
| `subsumes/` | [subsumes](https://github.com/georg-wolflein/subsumes) | the crate from crates.io | draft 2020-12 |
| `subsumes-python/` | subsumes | the package from PyPI | draft 2020-12 |

A checker is taken from a package index wherever it is published to one, at a pinned version. RWG is not published, so its adapter is compiled together with its sources.

## Licence

The adapters are MIT licensed like the rest of this repository, with one exception: **`rwg/` is licensed under GPL-3.0**, because it is compiled together with RWG, which is. [`rwg/LICENSE`](rwg/LICENSE) has the text. Nothing else in the repository links to RWG; the runner talks to every adapter as a separate process.

## A checker's folder

`checker.json` describes the checker, and [`schemas/checker.schema.json`](../schemas/checker.schema.json) is its schema:

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

| Key | Meaning |
| --- | --- |
| `label` | The checker's name in a report |
| `variant` | Optional: what tells the folder from another one with this label |
| `version` | The version the folder pins, as the report states it |
| `homepage` | Where the checker lives |
| `dialect` | What it reads: `2020-12`, `draft-07` or `draft-04` |
| `build` | The command that builds the adapter; run once, in the folder |
| `run` | The command that starts the adapter, in the folder |

Folders with the same `label` are variants of one checker. A report draws them in one colour and says whether they gave the same answers.

A checker that does not read draft 2020-12 gets every schema rewritten to its `dialect` by the runner (`subsumes_benchmark.compare.downgrade`): references are resolved and keywords renamed. Where the older draft cannot express a schema, the checker is not asked and the task counts as `unsupported`.

## The protocol

The adapter is a program that starts once and answers many requests, so that starting it is not part of any measured time. It reads its standard input and writes its standard output, one JSON document per line.

1. On start, the adapter prints `{"ready": true}`.
2. For every request line it prints one reply line.

A request names two files and the time allowed:

```json
{"a": "/scratch/a.json", "b": "/scratch/b.json", "timeout": 10.0}
```

The runner writes the two schemas of the task to these files before it asks, so an adapter never reads the corpus. The question is always whether `a` accepts every instance valid under `b`. The reply:

```json
{"answer": "yes", "seconds": 0.00042, "detail": null}
```

- **`answer`**: `yes` when A accepts every instance of B, `no` when it does not, `unknown` when the checker ran and declined, `error` when it failed or rejected a schema, `timeout` when it stopped itself after the time allowed.
- **`seconds`**: what the checker took, measured by the adapter from the two schemas as text to the answer. Parsing the text is part of it; reading the files is not.
- **`detail`**: optional, a short text for a person: a counterexample, the reason for declining, the error.
- **`reason`**: optional, with an `unknown`: what kind of reason the checker had, in a word or two that are the same for every task declined for it, such as the keyword it does not support. A report counts the declined tasks by it; `detail` has the reason in full.
- **`counterexample`**: optional, with a `no`: an instance that is valid under `b` and invalid under `a`, as JSON. The runner asks a validator whether it is one, and a `no` with a counterexample that is none counts as a wrong answer. Leave the key out where the checker gives none, since `null` is an instance.

```json
{"answer": "no", "seconds": 0.00042, "detail": "\"x\"", "counterexample": "x"}
{"answer": "unknown", "seconds": 0.00042, "detail": "#/uniqueItems in schema A is not supported", "reason": "uniqueItems"}
```

The validator is [jsonschema-rs](https://github.com/Stranger6667/jsonschema) for draft 2020-12 with `format` asserted. It is asked about the two schemas of the case as the corpus has them, also where the checker reads an older draft and got them rewritten.

Rules for an adapter:

- **Nothing but replies on the standard output.** A library that prints must be redirected to the standard error, which the runner keeps as a log next to the results.
- **Assert `format`** where the checker can, since the labels of the corpus hold with `format` asserted.
- **Survive an error.** Catch what the checker throws and reply `error`, so that the next request is answered by a warm process.
- **A timeout need not be handled.** The runner waits two seconds longer than the time allowed, then kills the adapter, counts the task as a timeout and starts the adapter again. An adapter that can stop a check itself replies `timeout` and stays warm.

## A checker in another repository

The folder of a checker can be anywhere: `subsumes-benchmark run` takes its path. So a checker can keep its adapter next to its own code, built from the working tree, and run it with the package from PyPI, as the Rust library [subsumes](https://github.com/georg-wolflein/subsumes) does to hold a change against the corpus. Its `checker.json` names the schema by a URL:

```json
{
  "$schema": "https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/schemas/checker.schema.json"
}
```

A run is named like the folder and goes to a folder of that name under `--out`.

## Adding a checker

1. Create the folder with `checker.json` and the adapter. Pin the checker's version, and commit a lock file where the toolchain has one.
2. Try it on a sample: `uv run subsumes-benchmark run checkers/<folder> --limit 300`.
3. Add the folder to the matrix in `.github/workflows/comparison.yml`, with the toolchain it needs, and to the table above.
4. Push the branch and run the sample for every checker on it: `gh workflow run comparison.yml --ref <branch> -f limit=300`.
