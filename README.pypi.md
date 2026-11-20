# subsumes-benchmark

The [subsumes benchmark corpus](https://github.com/georg-wolflein/subsumes-benchmark) for JSON Schema inclusion, and the command that runs a checker over it and reports on the run.

The corpus is pairs of draft 2020-12 schemas with known answers to one question: does schema A accept every instance that is valid under schema B? A checker is a program that answers it, and the [repository](https://github.com/georg-wolflein/subsumes-benchmark#comparing-checkers) compares the open-source ones.

The package of a version holds the corpus of that version, so the version pins both. Results measured on two versions are comparable exactly when their major and minor numbers match.

## Use

The command needs Python 3.14, which [uv](https://docs.astral.sh/uv/) fetches by itself.

```bash
# Unpack the corpus into corpus/.
uvx subsumes-benchmark==<version> corpus corpus

# Run a checker over every task; the results go to results/<folder of the checker>/.
uvx subsumes-benchmark==<version> run path/to/checker

# Hold the run against an earlier one, as a comment for a pull request.
uvx subsumes-benchmark==<version> diff results/checker --base base/checker

# Report on the runs of several checkers, with charts.
uvx --from 'subsumes-benchmark[report]==<version>' subsumes-benchmark report results
```

- **`corpus`** unpacks the corpus into a new or empty folder: one JSON file per case, in a folder per collection, below a folder per work that first published its pairs. The [repository](https://github.com/georg-wolflein/subsumes-benchmark#a-case) describes a case and the collections.

- **`run`** asks the checker both directions of every case, one task after the other, and writes one line per task to `results.jsonl`. Where the checker gives a counterexample with a no, a validator is asked whether it is one. [`result.schema.json`](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/schemas/result.schema.json) and [`run.schema.json`](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/schemas/run.schema.json) describe the two files of a run.
- **`diff`** holds one run against another of the same checker. It fails when an answer is wrong, when a task ended in an error, a crash or a timeout, and when a task that the other run answered is no longer answered.
- **`report`** compares the runs of several checkers: how many tasks each one solved, how often it was wrong, and how long it took.

## A checker

A checker is a folder with a `checker.json` and an adapter: a program that starts once, prints `{"ready": true}`, and then answers one request per line on its standard input with one line on its standard output. A request holds the two schemas and asks whether `a` accepts every instance that is valid under `b`.

```json
{"ready": true}
{"a": {"type": "string"}, "b": {"maxLength": 3}, "timeout": 10.0}
{"answer": false, "seconds": 0.00042, "counterexample": "x"}
```

The first line is the adapter's when it has started, the second a request, and the third the reply to it. An answer is `true`, `false` or `null`, as the label of a case is, and a reply without one says why: `{"failure": "error", "message": "…"}` or `{"failure": "timeout"}`.

[The documentation of the checkers](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md) has the keys of `checker.json`, the protocol in full, and the adapters of the checkers that the repository compares.

## Licences

The code is MIT licensed. The corpus keeps the licences of its sources, which its `collections.json` names for each collection: GPL-3.0 for the collections built from the artifact of *JSON Schema Inclusion through Refutational Normalization*, and MIT for the one built from the official JSON Schema Test Suite. The package carries the texts, and so does the corpus: the folder of each collection has its `LICENSE`.
