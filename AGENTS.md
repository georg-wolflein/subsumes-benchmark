This project is a benchmark corpus for JSON Schema inclusion checking (does schema A subsume schema B?) for draft 2020-12, plus the Python code that builds it.

## Tooling

Everything runs through `uv`. `make ci` runs what CI runs on a pull request: `ruff check`, `ruff format --check`, `ty check`, `pytest`. `make format` fixes what ruff can fix. Configuration lives in `pyproject.toml`; CI is `.github/workflows/ci.yml` (tests on Python 3.14, plus a `corpus` job that runs the slow tests over every schema of the corpus; `make test-corpus` runs them locally in a few minutes). `.github/workflows/release.yml` runs release-please, configured in `release-please-config.json`: it keeps a release pull request open, and publishes the release when that pull request is merged. `.github/workflows/pr-title.yml` checks the title of every pull request. `.github/workflows/comparison.yml` runs the checkers under `checkers/` over the corpus: over every task after a release or when started by hand, and over a sample on a pull request that carries the `comparison` label.

## Rules

- The built package must never contain benchmark data.
- Every change reaches `main` through a pull request; a ruleset rejects a direct push.
- Commit messages and pull request titles follow the Conventional Commits format.
- Pull requests are squash-merged, so the PR title becomes the commit message on `main`.
- The titles decide the next version, so the type says what a change does to the corpus: `!` when a reader has to change, `feat` when a label, a schema or the set of cases changes, even to correct a mistake, and `fix` for anything else worth a release. The README's section on development has the table.
- The release pull request raises the version. Never change the version in `pyproject.toml`, `uv.lock` or `.release-please-manifest.json` by hand.
- `corpus/` is generated; never edit it by hand. Change `collections.toml`, `overrides.toml` or the code under `src/`, then run `make corpus` (after `make sources`, once) and commit the result.
- A label that departs from upstream's needs an entry in `overrides.toml` with the reason. Nothing else may change a label. For a case built from the official test suite, upstream's label is what the suite's expected result gives.
- Every schema in the corpus is valid draft 2020-12 and every reference in it resolves. An upstream case that is not is left out through an `[[exclude]]` entry in `overrides.toml`, with the reason. So is a test case of the official test suite whose expected results are not those of draft 2020-12 with `format` asserted.
- The labels hold for draft 2020-12 with `format` asserted and patterns read in the dialect of the Rust `regex` crate. Do not assume ECMA-262 patterns, and do not use Python's `re` to decide what a pattern matches; `tests/validation.py` has the matcher.
- `a.json` is the schema that should accept everything and `b.json` the one whose instances must be accepted. Keep that orientation in every name: `a_subsumes_b`, `subsumes(a, b)`.
- The build uses the standard library only, and so does running a checker (`subsumes_benchmark.compare`). What only the tests need goes in the `dev` dependency group, and what only the report needs in the `report` group.
- `comparison/` and the part of the README between the `comparison` markers are written by the `Comparison` workflow; never edit them by hand.
- A checker is used from a package index at a pinned version wherever it is published to one. The `version` in its `checker.toml` is the version its folder pins.
- `checkers/rwg/` is GPL-3.0, because it is compiled together with RWG. Nothing outside that folder may link to RWG.

## Coding Conventions

- Use the narrowest practical type.
- `Sequence[T]` for variable-length collections. Use `tuple[...]` only for fixed-length positional data like `tuple[str, int]`, or where you actually need tuple behaviour. Don't write `tuple[T, ...]`.
- `Literal[...]` for small closed sets instead of bare `str`.
- PEP 695 type parameters: `def f[T: Base](x: T) -> T`, not a separate `TypeVar`. Applies to generic classes, functions, and aliases.
- Don't annotate with `dict` or `Any` when it is not really necessary. Don't annotate with `Any` when a better type is available or would be easy to create; a `dataclass` is usually that better type. JSON values are `subsumes_benchmark.Json`.
- Dataclasses for data holders instead of hand-written `__init__` and `__repr__`.
- `match` for closed-set dispatch on a `Literal` or a sealed class hierarchy, with a `case _: assert_never(x)` arm, so exhaustiveness is a typecheck failure rather than a silent fall-through.
- Classmethod factories over module-level constructors: `ClassName.create(...) -> Self`, not `_create_class_name(...)`.
- Docstrings use Google style. Omit types from `Args`/`Returns` and skip `Raises` unless crucial.
