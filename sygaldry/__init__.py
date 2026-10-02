"""
Public API for Sygaldry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .__version__ import __version__ as __version__
from .artificery import Artificery
from .artificery import resolve_config as resolve_config
from .cache import Instances
from .secrets import Secret

__author__ = "Rohan B. Dalton"
__all__ = (
    "Artificery",
    "load",
    "Secret",
)


def load(
    path: str | Path,
    *,
    cache: Instances | None = None,
    transient: bool = False,
    strict: bool = True,
    key: str | None = None,
) -> Any:
    """
    Load, interpolate, and resolve a config file.

    :param path: Path to a YAML or TOML config file. Managed resources require an Artificery scope.
    :param key: Optional dotted key to resolve instead of the whole graph.
    :param strict: Reject unknown constructor kwargs when True (the default).
    :param cache: Optional instance cache.
    :param transient: Isolate named sharing from any supplied cache; refs keep identity.
    :type path: str | pathlib.Path
    :type cache: Instances | None
    :type transient: bool
    :returns: Resolved configuration mapping.
    :rtype: dict[str, Any]
    """
    result = Artificery(path, cache=cache, transient=transient, strict=strict).resolve(key)
    return result


if __name__ == "__main__":
    pass
