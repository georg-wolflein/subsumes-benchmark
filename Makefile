.PHONY: ci lint format format-check typecheck test test-corpus sources corpus compare report

ci: lint format-check typecheck test  ## what CI runs on every change, without the slow corpus tests

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

format-check:
	uv run ruff format --check .

typecheck:
	uv run ty check

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
