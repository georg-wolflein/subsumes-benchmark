.PHONY: ci lint format format-check typecheck config test test-corpus sources corpus compare report

# The adapters under checkers/ that are checked like the code under src/: each Rust one is
# a crate of its own, and each Python one a script with an environment of its own.
RUST_ADAPTERS := $(wildcard checkers/*/Cargo.toml)
PYTHON_ADAPTERS := $(wildcard checkers/*/adapter.py)

ci: lint format-check typecheck config test  ## what CI runs on every change, without the slow corpus tests

lint:
	uv run ruff check .
	for manifest in $(RUST_ADAPTERS); do \
		cargo clippy --manifest-path $$manifest --locked --all-targets -- --deny warnings || exit 1; \
	done

format:
	uv run ruff format .
	uv run ruff check --fix .
	for manifest in $(RUST_ADAPTERS); do cargo fmt --manifest-path $$manifest || exit 1; done

format-check:
	uv run ruff format --check .
	for manifest in $(RUST_ADAPTERS); do cargo fmt --manifest-path $$manifest --check || exit 1; done

typecheck:
	uv run ty check
	for adapter in $(PYTHON_ADAPTERS); do \
		uv sync --quiet --locked --script $$adapter && \
		uv run ty check --python "$$(uv python find --script $$adapter)" $$adapter || exit 1; \
	done

config:  ## the schemas are valid, and every configuration file is valid under its schema
	uv run check-jsonschema --check-metaschema schemas/*.schema.json
	uv run check-jsonschema --schemafile schemas/collections.schema.json collections.json
	uv run check-jsonschema --schemafile schemas/overrides.schema.json overrides.json
	uv run check-jsonschema --schemafile schemas/checker.schema.json checkers/*/checker.json

test:
	uv run pytest

test-corpus:  ## the slow tests: every schema is valid, every reference resolves, every checkable label holds
	uv run pytest -m slow

sources:  ## fetch the upstream sources; they are opt-in submodules and only needed to rebuild
	git submodule update --init --checkout sources/json-schema-test-suite sources/inclusion-artifact

corpus:  ## rebuild corpus/ from the upstream sources
	uv run python -m subsumes_benchmark

compare:  ## run every checker under checkers/ over the corpus into results/; hours, and needs their toolchains
	for folder in checkers/*/; do uv run python -m subsumes_benchmark.compare run "$$(basename "$$folder")" || exit 1; done

report:  ## write the report on the runs in results/ to comparison/
	uv run --group report python -m subsumes_benchmark.compare report results
