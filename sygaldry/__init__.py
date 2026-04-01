"""
Public API for Sygaldry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .__version__ import __version__
from .artificery import Artificery, resolve_config
from .cache import Instances

__author__ = "Rohan B. Dalton"
__all__ = (
    "Artificery",
    "load",
)


def load(
    path: str | Path,
    *,
    cache: Instances | None = None,
    transient: bool = False,
) -> dict[str, Any]:
    """
    Load, interpolate, and resolve a config file.

    :param path: Path to a YAML or TOML config file.
    :param cache: Optional instance cache.
    :param transient: If True, bypass caching.
    :type path: str | pathlib.Path
    :type cache: Instances | None
    :type transient: bool
    :returns: Resolved configuration mapping.
    :rtype: dict[str, Any]
    """
    return Artificery(path, cache=cache, transient=transient).resolve()


if __name__ == "__main__":
    pass
