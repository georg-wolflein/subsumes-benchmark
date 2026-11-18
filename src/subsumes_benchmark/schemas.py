"""``python -m subsumes_benchmark.schemas``: write the schemas of the configuration files.

A schema is generated from the Pydantic model that reads the file, so the two cannot say
different things. Run from the repository root (``make schemas``) after changing a model, and
commit the result.
"""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic.json_schema import GenerateJsonSchema

from subsumes_benchmark.build import Collections, Overrides, write_json
from subsumes_benchmark.compare.checkers import Checker
from subsumes_benchmark.convert import DRAFT_2020_12

if TYPE_CHECKING:
    from collections.abc import Mapping

    from pydantic.json_schema import CoreSchemaOrField

    from subsumes_benchmark import Json
    from subsumes_benchmark.config import ConfigFile

SCHEMAS = Path("schemas")

# The file under schemas/ of each configuration file's model.
MODELS: Mapping[str, type[ConfigFile]] = {
    "collections.schema.json": Collections,
    "overrides.schema.json": Overrides,
    "checker.schema.json": Checker,
}

ID = "https://github.com/georg-wolflein/subsumes-benchmark/blob/main/schemas"


class _Generator(GenerateJsonSchema):
    """Leaves out the title of a property, which only repeats its name."""

    def field_title_should_be_set(self, schema: CoreSchemaOrField) -> bool:
        return False


def unwrapped(node: Json) -> Json:
    """The schema with every description as flowing text: a docstring is broken into lines."""
    if isinstance(node, list):
        return [unwrapped(item) for item in node]
    if not isinstance(node, dict):
        return node
    return {
        key: "\n\n".join(" ".join(paragraph.split()) for paragraph in value.split("\n\n"))
        if key == "description" and isinstance(value, str)
        else unwrapped(value)
        for key, value in node.items()
    }


def schema_of(name: str) -> Json:
    """The schema that ``schemas/<name>`` holds."""
    generated = MODELS[name].model_json_schema(schema_generator=_Generator)
    return unwrapped({"$schema": DRAFT_2020_12, "$id": f"{ID}/{name}", **generated})


def main() -> None:
    for name in MODELS:
        write_json(SCHEMAS / name, schema_of(name))


if __name__ == "__main__":
    main()
