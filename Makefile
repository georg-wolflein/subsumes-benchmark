.PHONY: ci lint format format-check typecheck config test sources corpus models compare report archive

# The adapters under checkers/ that are checked like the code under src/: each Rust one is
# a crate of its own, and each Python one a script with an environment of its own.
RUST_ADAPTERS := $(wildcard checkers/*/Cargo.toml)
PYTHON_ADAPTERS := $(wildcard checkers/*/adapter.py)

# The schemas under schemas/ that a model is generated from, each with the name of its model.
MODELS := collections:CollectionsSpec overrides:OverridesSpec derived:DerivedSpec checker:CheckerSpec \
	case:CaseSpec ready:ReadySpec request:RequestSpec reply:ReplySpec result:ResultSpec run:RunSpec

ci: lint format-check typecheck config test  ## what CI runs on every change

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

config:  ## the schemas are valid, every configuration file is valid under its schema, and the generated models are current
	uv run check-jsonschema --check-metaschema schemas/*.schema.json
	uv run check-jsonschema --schemafile schemas/collections.schema.json collections.json
	uv run check-jsonschema --schemafile schemas/overrides.schema.json overrides.json
	uv run check-jsonschema --schemafile schemas/derived.schema.json derived.json
	uv run check-jsonschema --schemafile schemas/checker.schema.json checkers/*/checker.json
	for model in $(MODELS); do \
		uv run datamodel-codegen --check --input schemas/$${model%%:*}.schema.json \
			--output src/subsumes_benchmark/generated/$${model%%:*}.py --class-name $${model##*:} || exit 1; \
	done

test:
	uv run pytest

sources:  ## fetch the upstream sources; they are opt-in submodules and only needed to rebuild
	git submodule update --init --checkout sources/json-schema-test-suite sources/inclusion-artifact

corpus:  ## rebuild corpus/ from the upstream sources, and the table of the collections in the README
	uv run python -m subsumes_benchmark
	uv run python -m subsumes_benchmark.table corpus | scripts/readme-part.sh collections

archive:  ## pack corpus/ into the file that a built package holds, so that `uv build` after it builds a package with the corpus
	uv run python -m subsumes_benchmark.archive corpus src/subsumes_benchmark/corpus.tar.zst

models:  ## write src/subsumes_benchmark/generated/ from the schemas; the options are in pyproject.toml
	for model in $(MODELS); do \
		uv run datamodel-codegen --input schemas/$${model%%:*}.schema.json \
			--output src/subsumes_benchmark/generated/$${model%%:*}.py --class-name $${model##*:} || exit 1; \
	done

compare:  ## run every checker under checkers/ over the corpus into results/; hours, and needs their toolchains
	for folder in checkers/*/; do uv run subsumes-benchmark run "$$folder" || exit 1; done

report:  ## write the report on the runs in results/ to comparison/
	uv run --extra report subsumes-benchmark report results
