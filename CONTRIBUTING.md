# Contributing

Everything runs through [uv](https://docs.astral.sh/uv/). Every change reaches `main` through a pull request.

## Rebuild the corpus

```bash
uv sync
make sources   # fetches the two upstream repositories, about 900 MB
make corpus    # about 15 seconds
```

`corpus/` is generated, except its `README.md`: change `collections.json`, `overrides.json` or the code under `src/`, run `make corpus` and commit the result. `make corpus` also writes the parts of the main README that the corpus decides: the list of the collections, their number and the number of tasks with a label.

The submodules under `sources/` are marked `update = none`, so cloning this repository does not fetch them; `make sources` does. Their commits pin what the corpus is built from. The build reads `derived.json` as it is and runs no checker.

## Checks

```bash
make ci       # what CI runs on a pull request
make format   # apply the fixes and the formatting of ruff and cargo fmt
make models   # rewrite the generated models after a change to a schema
make readme   # make the plots and the table again, and write the parts of the README that are written from data
```

`make ci` lints and type-checks the code and the adapters under `checkers/`, so it needs `cargo`. It holds every configuration file against its schema, checks that the README is what the corpus and the comparison give, and it runs the tests, which read every case of the committed corpus in under a minute.

## Pull requests

A title follows [Conventional Commits](https://www.conventionalcommits.org/), and a pull request is squash-merged, so its title becomes the commit on `main`. The titles merged since the last release decide the next version. So the type says what a change does to the corpus, by [what a version means](corpus/README.md#versions), and not why it was made:

| Title | Version | For |
| --- | --- | --- |
| `feat!:`, or another type with `!` | Major, or minor before 1.0.0 | A change that a reader has to follow |
| `feat:` | Minor | A change to a label, a schema or the set of cases, also where it corrects a mistake |
| `fix:`, `perf:`, `revert:`, `build:` | Patch | Anything else that is worth a release |

A pull request of another type, such as `docs`, `ci` or `chore`, goes out with the next release.

[release-please](https://github.com/googleapis/release-please) keeps one pull request open that raises the version. Merging it publishes the release: the archive of the corpus as a file of the release, and the package with the archive in it on PyPI. Never change the version by hand.

## Derive labels

A label that upstream does not give comes from runs of checkers over the questions without one, by the rules of [Derived labels](docs/construction.md#derived-labels). `--unlabelled` asks only those questions. Such a run is not measured, so it needs no warm-up and may run several processes side by side:

```bash
SUBSUMES_BUDGET=1000000000 uv run subsumes-benchmark run checkers/subsumes --unlabelled --warmup 0 --jobs 8 --timeout 1800 --out results/unlabelled
uv run subsumes-benchmark run checkers/jsoncompat --unlabelled --warmup 0 --jobs 2 --timeout 60 --out results/unlabelled
uv run subsumes-benchmark derive results/unlabelled/subsumes results/unlabelled/jsoncompat   # and the folder of any other run
make corpus
```

`derive` writes `derived.json`; never edit it by hand. A run reads the corpus while it works, so the corpus is rebuilt only after the last run has ended. The adapters of subsumes read `SUBSUMES_BUDGET`, the work a check may take in steps; unset, a check has the library's default of 10 million steps, which is what the comparison measures.

## Repository layout

| Path | Content |
| --- | --- |
| `corpus/` | The corpus: generated and committed. Its `README.md` is the one file in it that is written by hand |
| `collections.json` | The collections, the work that each was first published in and the upstream dataset that each is built from |
| `overrides.json` | Every departure from upstream, with the reason: the cases left out and the labels changed |
| `derived.json` | The labels that upstream does not give, each with what shows it |
| `schemas/` | The schemas of a case, of the configuration files, of the protocol between the runner and an adapter, of the files of a run and of the comparison of a report. They say what each key means |
| `src/subsumes_benchmark/` | The build, and `validation`, which validates an instance the way the corpus reads a schema |
| `src/subsumes_benchmark/generated/` | The models that read what the schemas describe: generated from them, never edited by hand |
| `src/subsumes_benchmark/compare/` | Running a checker over the tasks, the report on runs, and deriving labels |
| `scripts/` | `readme.py`, which writes the parts of the README that are written from data, each between its two markers |
| `sources/` | The upstream repositories as submodules, fetched only to rebuild |
| `checkers/` | One folder per checker of the comparison, with the adapter that makes it answer |
| `comparison/` | The latest comparison: `comparison.json`, written by the `Comparison` workflow, and the plot and the table that `subsumes-benchmark report` makes from it |
| `docs/` | How the corpus is built |
| `tests/` | The layout of the corpus, the validity of its schemas, the labels that can be checked, the runner and the report |
