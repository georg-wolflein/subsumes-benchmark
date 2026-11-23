This project is a benchmark corpus for JSON Schema inclusion checking (does schema A subsume schema B?) for draft 2020-12, plus the Python code that builds it.

## Tooling

Use `uv` for Python commands. Run `make ci` for the CI checks and `make format` to apply formatting and automatic fixes. See [CONTRIBUTING.md](CONTRIBUTING.md) for development commands and workflows.

## Rules

- The package holds benchmark data only as `src/subsumes_benchmark/corpus.tar.zst`. Generate it with `make archive`; never commit the archive.
- Make changes through pull requests. Use Conventional Commits for commits and PR titles, following the corpus-specific versioning rules in [CONTRIBUTING.md](CONTRIBUTING.md#pull-requests). Never bump versions manually; release-please owns them.
- A collection’s origin identifies the work that first published its pairs as inclusion questions, not the source the build reads. Keep that distinction in `collections.json`.
- `corpus/` is generated, except its `README.md`, which is written by hand and which a build leaves as it is; never edit anything else in it by hand. Every link in that page to something outside `corpus/` is a full URL, since the page travels in the archive. Change `collections.json`, `overrides.json`, `derived.json` or the code under `src/`, then run `make corpus` (after `make sources`, once) and commit the result.
- A label that departs from upstream's needs an entry under `override` in `overrides.json` with the reason. Nothing else may change a label. For a case built from the official test suite, upstream's label is what the suite's expected result gives.
- No two cases may hold the same two schemas, in either order. `overrides.json` and its exclusions name upstream cases; `derived.json` names cases of the corpus.
- A generated collection is built by a generator under `src/` from no source, and its case is of the kind `generated`, with `generated` in place of `upstream`. Its labels are known by construction, and the tests check them: every `false` by a counterexample that both validators of `subsumes_benchmark.validation` confirm, and every label of the small sizes from an instance of every class that the two schemas tell apart. Every member of a family has a twin whose answer flips.
- A label where a case has none comes from `derived.json`, with what shows it. `subsumes-benchmark derive` writes the file from runs of checkers with `--unlabelled`; never edit it by hand. A label is `false` only with a counterexample that both validators of `subsumes_benchmark.validation` confirm, and `true` only where two checkers say yes, none says no, and the schemas use neither a pattern nor a format. One checker's yes is never a label, and a case that `overrides.json` lists gets none.
- Every schema in the corpus is valid draft 2020-12 and every reference in it resolves. The schema of a case requires the first, by referencing the metaschema, and a keyword that asserts nothing, such as `deprecated`, is no exception. An upstream case that is not is left out through an entry under `exclude` in `overrides.json`, with the reason. So is a test case of the official test suite whose expected results are not those of draft 2020-12 with `format` asserted.
- The labels hold for draft 2020-12 with `format` asserted and patterns read as ECMA-262 regular expressions with the `u` flag, which is what the specification recommends. Do not use Python's `re` to decide what a pattern matches, nor Python's format checkers to decide what a format accepts; `subsumes_benchmark.validation` has the validator.
- In a case, `a` is the schema that should accept everything and `b` the one whose instances must be accepted. Keep that orientation in every name: `a_subsumes_b`, `subsumes(a, b)`.
- The build uses Pydantic, which reads the configuration files, and otherwise the standard library only. Running a checker (`subsumes_benchmark.compare`) uses `jsonschema-rs` besides, which validates the counterexamples that a checker gives; its version is pinned exactly, since it decides which of them count. What only the tests need goes in the `dev` dependency group, and what only the report needs in the extra `report`, so that an installed package can have it. What validating an instance as the labels read a schema needs besides goes in the `validation` group, which `dev` includes: the tests need it, and so does deriving a label, which is done in a checkout.
- `README.md` is the page of the repository and of the package on PyPI, so every link and picture in it is a full URL. It stays short: what the benchmark is, the results, the collections, and how to get the corpus and run a checker. What a case holds and what the labels mean is in `corpus/README.md`, how the corpus is built in `docs/construction.md`, the checkers, the commands and the protocol in `checkers/README.md`, and development in `CONTRIBUTING.md`.
- Never edit `comparison/` or the marked generated parts of `README.md` by hand. The `Comparison` workflow writes `comparison/comparison.json`; `make readme` regenerates the plots, table and README parts from the existing comparison and corpus without rerunning checkers. README generation belongs in `scripts/readme.py`, not the package. Keep corpus counts generated, except for the tables in `docs/construction.md`.
- The command takes every path relative to the working directory and assumes no checkout around it, since it also runs as an installed package.
- Start changes to configuration, protocol and result formats in their schemas under `schemas/`. Never edit `src/subsumes_benchmark/generated/` by hand: run `make models` after schema changes and commit the result. Put validation that a schema cannot express in a subclass of the generated model. Run `make config` to check schemas, configuration and model freshness.
- Omit keys that do not apply. Use `null` only as a value: an answer declined, a missing label, or a null counterexample. Keep field meanings consistent across schemas.
- Shared schema definitions are intentionally repeated because models are generated one schema at a time. Keep the copies consistent; `tests/test_protocol.py` checks them.
- Generated models may accept more than their schemas allow. Do not tighten them just for that; serialized output must conform to the schemas.
- A checker is used from a package index at a pinned version wherever it is published to one. The `version` in its `checker.json` is the version its folder pins.

## Coding Conventions

- `Sequence[T]` for variable-length collections. Use `tuple[...]` only for fixed-length positional data like `tuple[str, int]`, or where you actually need tuple behaviour. Don't write `tuple[T, ...]`.
- `Literal[...]` for small closed sets instead of bare `str`.
- PEP 695 type parameters: `def f[T: Base](x: T) -> T`, not a separate `TypeVar`. Applies to generic classes, functions, and aliases.
- Don't annotate with `dict` or `Any` when it is not really necessary. Don't annotate with `Any` when a better type is available or would be easy to create; a `dataclass` is usually that better type. JSON values are `subsumes_benchmark.Json`.
- Dataclasses for data holders instead of hand-written `__init__` and `__repr__`.
- `match` for closed-set dispatch on a `Literal` or a sealed class hierarchy, with a `case _: assert_never(x)` arm, so exhaustiveness is a typecheck failure rather than a silent fall-through.
- Classmethod factories over module-level constructors: `ClassName.create(...) -> Self`, not `_create_class_name(...)`.
- Docstrings use Google style. Omit types from `Args`/`Returns` and skip `Raises` unless crucial.
- Put all `import` statements at the top of the module.
