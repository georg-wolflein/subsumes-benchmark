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

Each of the three lines has a schema under [`schemas/`](../schemas): [`ready`](../schemas/ready.schema.json), [`request`](../schemas/request.schema.json) and [`reply`](../schemas/reply.schema.json). They say what a line holds, key by key, and the runner writes a request and reads the other two with models that are generated from them. Two rules hold in all of them, and in the files of a run: a key that does not apply is left out and not written as `null`, and no line has a key that its schema does not name.

A request holds two schemas and the time allowed:

```json
{"a": {"type": "string"}, "b": {"maxLength": 3}, "timeout": 10.0}
```

`a` and `b` are the schemas themselves, as JSON values on the one line of the request. Nothing is written to a file, and an adapter never reads the corpus. The question is always whether `a` accepts every instance valid under `b`.

A reply is an answer to that question, or it says why there is none. An answer is `true`, `false` or `null`, as the label of a case is:

```json
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

- **`seconds`**: what the checker took, measured by the adapter. It covers parsing each schema once, and the check, which is what someone pays who holds two schemas as text. An adapter whose checker takes a parsed schema starts the clock before it parses the request, since that parses the two. An adapter whose checker takes text writes each schema back to text first, and starts the clock then.
- **`counterexample`**: an instance that is valid under `b` and invalid under `a`, as JSON. The runner asks a validator whether it is one, and a no with a counterexample that is none counts as a wrong answer. Leave the key out where the checker gives none, since `null` is an instance. A label can be [derived](../README.md#derived-labels) from a counterexample.
- **`reason`**: what kind of reason the checker had to decline, in a word or two that are the same for every task declined for it, such as the keyword it does not support. A report counts the declined tasks by it.
- **`message`**: a text for a person: what the checker says about its no, the reason for declining in full, the error.

The validator is [jsonschema-rs](https://github.com/Stranger6667/jsonschema) for draft 2020-12 with `format` asserted. It is asked about the two schemas of the case as the corpus has them, also where the checker reads an older draft and got them rewritten.

Rules for an adapter:

- **Nothing but replies on the standard output.** A library that prints must be redirected to the standard error, which the runner keeps as a log next to the results.
- **Assert `format`** where the checker can, since the labels of the corpus hold with `format` asserted.
- **Only the keys of the reply.** Each of the five has its own keys, as the table has them: a `counterexample` belongs to a no and a `reason` to a `null`. A line that is no reply by the schema counts as a crash of the adapter: the runner records the task so, with what is wrong with the line, and starts the adapter again.
- **Survive an error.** Catch what the checker throws and reply with the failure `error`, so that the next request is answered by a warm process.
- **A timeout need not be handled.** The runner waits two seconds longer than the time allowed, then kills the adapter, counts the task as a timeout and starts the adapter again. An adapter that can stop a check itself replies with the failure `timeout` and stays warm.

## A checker in another repository

The folder of a checker can be anywhere: `subsumes-benchmark run` takes its path. So a checker can keep its adapter next to its own code, built from the working tree, and run it with the package from PyPI, as the Rust library [subsumes](https://github.com/georg-wolflein/subsumes) does to hold a change against the corpus. Its `checker.json` names the schema by a URL:

```json
{
  "$schema": "https://raw.githubusercontent.com/georg-wolflein/subsumes-benchmark/main/schemas/checker.schema.json"
}
```

A run is named like the folder and goes to a folder of that name under `--out`.

## A run that is to find labels

`--unlabelled` asks only the tasks that the corpus has no label for. Such a run is not measured, so it needs no warm-up and may run several processes side by side:

```bash
uv run subsumes-benchmark run checkers/jsoncompat --unlabelled --warmup 0 --jobs 4 --out results/unlabelled
```

The adapters of subsumes read `SUBSUMES_BUDGET`, the work a check may take in steps. Unset, a check has the library's default of 10 million steps, which is what a user gets and what the comparison measures.

## Adding a checker

1. Create the folder with `checker.json` and the adapter. Pin the checker's version, and commit a lock file where the toolchain has one.
2. Try it on a sample: `uv run subsumes-benchmark run checkers/<folder> --limit 300`.
3. Add the folder to the matrix in `.github/workflows/comparison.yml`, with the toolchain it needs, and to the table above.
4. Push the branch and run the sample for every checker on it: `gh workflow run comparison.yml --ref <branch> -f limit=300`.
