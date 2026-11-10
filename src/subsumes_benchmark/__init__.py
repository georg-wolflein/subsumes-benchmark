"""Builds the JSON Schema inclusion benchmark corpus under ``corpus/`` from its upstream sources."""

type Json = dict[str, Json] | list[Json] | str | int | float | bool | None
"""A JSON value as ``json.load`` produces it."""
