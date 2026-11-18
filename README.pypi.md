# subsumes-benchmark

Runs a JSON Schema inclusion checker over the [subsumes benchmark corpus](https://github.com/georg-wolflein/subsumes-benchmark) and reports on the run.

The corpus is pairs of draft 2020-12 schemas with known answers to one question: does schema A accept every instance that is valid under schema B? A checker is a program that answers it, and the [repository](https://github.com/georg-wolflein/subsumes-benchmark#comparing-checkers) compares the open-source ones.

> [!NOTE]
> The corpus is not part of this package. Each [release](https://github.com/georg-wolflein/subsumes-benchmark/releases) of the repository carries it as an archive, and the package of a version is made for the corpus of that version.

## Use

The command needs Python 3.14, which [uv](https://docs.astral.sh/uv/) fetches by itself.

```bash
# The corpus of the version that the package has, unpacked into corpus/.
curl -fsSLO https://github.com/georg-wolflein/subsumes-benchmark/releases/download/v<version>/corpus.tar.zst
zstd -dc corpus.tar.zst | tar -xf -

# Run a checker over every task; the results go to results/<folder of the checker>/.
uvx subsumes-benchmark==<version> run path/to/checker --corpus corpus

# Hold the run against an earlier one, as a comment for a pull request.
uvx subsumes-benchmark==<version> diff results/checker --base base/checker

# Report on the runs of several checkers, with charts.
uvx --from 'subsumes-benchmark[report]==<version>' subsumes-benchmark report results --corpus corpus
```

- **`run`** asks the checker both directions of every case, one task after the other, and writes one line per task to `results.jsonl`. Where the checker gives a counterexample with a no, a validator is asked whether it is one.
- **`diff`** holds one run against another of the same checker. It fails when an answer is wrong, when a task ended in an error, a crash or a timeout, and when a task that the other run answered is no longer answered.
- **`report`** compares the runs of several checkers: how many tasks each one solved, how often it was wrong, and how long it took.

## A checker

A checker is a folder with a `checker.json` and an adapter: a program that starts once, prints `{"ready": true}`, and then answers one request per line on its standard input with one line on its standard output.

```json
{"a": "/scratch/a.json", "b": "/scratch/b.json", "timeout": 10.0}
{"answer": "no", "seconds": 0.00042, "counterexample": "x"}
```

[The documentation of the checkers](https://github.com/georg-wolflein/subsumes-benchmark/blob/main/checkers/README.md) has the keys of `checker.json`, the protocol in full, and the adapters of the checkers that the repository compares.
