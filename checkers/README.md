# Checkers

Each folder here makes one inclusion checker answer the tasks of the corpus, so that `python -m subsumes_benchmark.compare` can run them all the same way. The [README](../README.md#comparing-checkers) says how to run a comparison and where its report goes.

| Folder | Checker | Used through | Reads |
| --- | --- | --- | --- |
| `confluent/` | The JSON Schema compatibility check of [Confluent Schema Registry](https://github.com/confluentinc/schema-registry) | `kafka-json-schema-provider` from Confluent's Maven repository | draft 2020-12 |
| `jsoncompat/` | [jsoncompat](https://github.com/ostrowr/jsoncompat) | the crate from crates.io | draft 2020-12 |
| `jsoncompat-python/` | jsoncompat | the package from PyPI | draft 2020-12 |
| `jsonsubschema/` | [jsonsubschema](https://github.com/IBM/jsonsubschema) | the package from PyPI | draft-04 |
| `rwg/` | [RWG](https://gitlab.lip6.fr/benali1/refutationalnormalizationforjsonschema), the tool of *JSON Schema Inclusion through Refutational Normalization* | its sources, in the submodule `sources/inclusion-artifact` | draft-07 |

A checker is taken from a package index wherever it is published to one, at a pinned version. RWG is not published, so its adapter is compiled together with its sources.

## Licence

The adapters are MIT licensed like the rest of this repository, with one exception: **`rwg/` is licensed under GPL-3.0**, because it is compiled together with RWG, which is. [`rwg/LICENSE`](rwg/LICENSE) has the text. Nothing else in the repository links to RWG; the runner talks to every adapter as a separate process.

## A checker's folder

`checker.toml` describes the checker:

```toml
label = "jsoncompat"            # the checker's name in a report
variant = "Rust"                # optional: what tells it from another folder with this label
version = "0.6.0"               # the version the folder pins, as the report states it
homepage = "https://github.com/ostrowr/jsoncompat"
dialect = "2020-12"             # what it reads: "2020-12", "draft-07" or "draft-04"
build = ["cargo", "build", "--release", "--locked"]   # run once, in the folder
run = ["target/release/adapter"]                      # starts the adapter, in the folder
```

Folders with the same `label` are variants of one checker. A report draws them in one colour and says whether they gave the same answers.

A checker that does not read draft 2020-12 gets every schema rewritten to its `dialect` by the runner (`subsumes_benchmark.compare.downgrade`): references are resolved and keywords renamed. Where the older draft cannot express a schema, the checker is not asked and the task counts as `unsupported`.

## The protocol

The adapter is a program that starts once and answers many requests, so that starting it is not part of any measured time. It reads its standard input and writes its standard output, one JSON document per line.

1. On start, the adapter prints `{"ready": true}`.
2. For every request line it prints one reply line.

A request names two files and the time allowed:

```json
{"a": "/path/to/a.json", "b": "/path/to/b.json", "timeout": 10.0}
```

The question is always whether `a` accepts every instance valid under `b`. The reply:

```json
{"answer": "yes", "seconds": 0.00042, "detail": null}
```

- **`answer`**: `yes` when A accepts every instance of B, `no` when it does not, `unknown` when the checker ran and declined, `error` when it failed or rejected a schema, `timeout` when it stopped itself after the time allowed.
- **`seconds`**: what the checker took, measured by the adapter from the two schemas as text to the answer. Parsing the text is part of it; reading the files is not.
- **`detail`**: optional, a short text for a person: a counterexample, the reason for declining, the error.

Rules for an adapter:

- **Nothing but replies on the standard output.** A library that prints must be redirected to the standard error, which the runner keeps as a log next to the results.
- **Assert `format`** where the checker can, since the labels of the corpus hold with `format` asserted.
- **Survive an error.** Catch what the checker throws and reply `error`, so that the next request is answered by a warm process.
- **A timeout need not be handled.** The runner waits two seconds longer than the time allowed, then kills the adapter, counts the task as a timeout and starts the adapter again. An adapter that can stop a check itself replies `timeout` and stays warm.

## Adding a checker

1. Create the folder with `checker.toml` and the adapter. Pin the checker's version, and commit a lock file where the toolchain has one.
2. Try it on a sample: `uv run python -m subsumes_benchmark.compare run <folder> --limit 300`.
3. Add the folder to the matrix in `.github/workflows/comparison.yml`, with the toolchain it needs, and to the table above.
4. Push the branch and run the sample for every checker on it: `gh workflow run comparison.yml --ref <branch> -f limit=300`.
