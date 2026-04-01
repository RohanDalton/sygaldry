from __future__ import annotations

__author__ = "Rohan B. Dalton"

import importlib
from typing import Optional

from .errors import ImportResolutionError

RESERVED_KEYS = frozenset(
    {
        "_type",
        "_func",
        "_args",
        "_kwargs",
        "_instance",
        "_ref",
        "_deep",
        "_include",
        "_entries",
        "_call",
    }
)


def import_dotted_path(
    dotted_path: str,
    *,
    file_path: str | None = None,
    config_path: str | None = None,
) -> object:
    """
    Import a dotted path and return the target object.
    Resolves the longest importable module prefix and then walks remaining attributes.
    Raising and ImportResolutionError with context if it fails.

    :param dotted_path: Fully-qualified dotted import path.
    :type dotted_path: str
    :param file_path: Source config file path, if known.
    :type file_path: str | None
    :param config_path: Dotted config path for context.
    :type config_path: str | None
    :returns: Imported module attribute or callable.
    :rtype: object
    :raises ImportResolutionError: If the module or attribute cannot be imported.
    """
    if not dotted_path or not isinstance(dotted_path, str):
        raise ImportResolutionError(
            "Dotted path must be a non-empty string.",
            file_path=file_path,
            config_path=config_path,
        )

    parts = dotted_path.split(".")
    module = None
    module_path = None

    for idx in range(len(parts), 0, -1):
        candidate = ".".join(parts[:idx])
        try:
            module = importlib.import_module(candidate)
        except Exception:
            continue
        else:
            module_path = candidate
            attributes = parts[idx:]
            break

    if module is None or module_path is None:
        raise ImportResolutionError(
            f"Failed to import module for dotted path '{dotted_path}'.",
            file_path=file_path,
            config_path=config_path,
        )
    else:
        target: object = module
        for attribute in attributes:
            try:
                target = getattr(target, attribute)
            except AttributeError as exc:
                raise ImportResolutionError(
                    f"Failed to resolve attribute '{attribute}' from '{module_path}' for dotted path '{dotted_path}'.",
                    file_path=file_path,
                    config_path=config_path,
                ) from exc

        return target


if __name__ == "__main__":
    pass
