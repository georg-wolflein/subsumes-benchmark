"""What the configuration files have in common.

Each of them is a JSON file with a schema under ``schemas/``, written by hand. The Pydantic
models that read the files are generated from the schemas into ``subsumes_benchmark.generated``
(``make models``), so a file that is not what its schema says does not get read.
"""

from typing import TYPE_CHECKING, Self

from pydantic import BaseModel, ConfigDict, ValidationError

if TYPE_CHECKING:
    from pathlib import Path


class ConfigError(Exception):
    pass


class Config(BaseModel):
    """What every generated model extends: a part of a configuration file, or a whole one."""

    model_config = ConfigDict(frozen=True, strict=True)

    @classmethod
    def read(cls, path: Path) -> Self:
        try:
            return cls.model_validate_json(path.read_bytes())
        except FileNotFoundError as error:
            raise ConfigError(f"{path} does not exist") from error
        except ValidationError as error:
            raise ConfigError(f"{path}: {error}") from error
