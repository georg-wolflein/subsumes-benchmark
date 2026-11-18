"""What the configuration files have in common.

Each of them is a JSON file that Pydantic reads into a model, so a file that is not what its
model says does not get read. The schemas under ``schemas/`` are generated from the same
models (``subsumes_benchmark.schemas``), for an editor to check and complete a file with.
"""

from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, ValidationError

if TYPE_CHECKING:
    from pathlib import Path


class ConfigError(Exception):
    pass


class Config(BaseModel):
    """A part of a configuration file.

    The docstring of a class and of each of its attributes is the description in the schema.
    """

    model_config = ConfigDict(
        frozen=True, extra="forbid", strict=True, use_attribute_docstrings=True
    )


class ConfigFile(Config):
    """A whole configuration file. A subclass says which schema the file names as ``$schema``."""

    @classmethod
    def read(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_bytes())
        except FileNotFoundError as error:
            raise ConfigError(f"{path} does not exist") from error
        except ValidationError as error:
            raise ConfigError(f"{path}: {error}") from error
