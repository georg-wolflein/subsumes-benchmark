This project holds a benchmark corpus for JSON Schema inclusion (does schema A accept every instance valid under schema B?) under `corpus/`, and the Python code that builds it from the upstream sources.

## Tooling

Everything runs through `uv`. `make ci` runs what CI runs on every change: `ruff check`, `ruff format --check`, `ty check`, `pytest`. `make test-corpus` runs the slow tests, which read every schema of the corpus and take about three minutes; CI runs them as a separate job. `make format` fixes what ruff can fix. Configuration lives in `pyproject.toml`; CI is `.github/workflows/ci.yml`.

## Rules

- `corpus/` is generated; never edit it by hand. Change `collections.toml`, `overrides.toml` or the code under `src/`, then run `make corpus` (after `make sources`, once) and commit the result.
- A label that departs from upstream's needs an entry in `overrides.toml` with the reason. Nothing else may change a label.
- The labels hold for draft 2020-12 with `format` asserted and patterns read in the dialect of the Rust `regex` crate. Do not assume ECMA-262 patterns, and do not use Python's `re` to decide what a pattern matches; `tests/validation.py` has the matcher.
- `a.json` is the schema that should accept everything and `b.json` the one whose instances must be accepted. Keep that orientation in every name: `a_subsumes_b`, `subsumes(a, b)`.
- The build uses the standard library only. What only the tests need goes in the `dev` dependency group.
- Commit messages follow the Conventional Commits format.

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
