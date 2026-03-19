"""
Public API for Sygaldry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .cache import Instances
from .artificery import Artificery
from .loader import load_config
from .resolver import resolve_config

__author__ = "Rohan B. Dalton"
__all__ = (
    "Artificery",
    "load",
)


def load(
    path: str | Path,
    *,
    cache: Optional[Instances] = None,
    transient: bool = False,
) -> Dict[str, Any]:
    """Load, interpolate, and resolve a config file.

    :param path: Path to a YAML or TOML config file.
    :param cache: Optional instance cache.
    :param transient: If True, bypass caching.
    :type path: str | pathlib.Path
    :type cache: Instances | None
    :type transient: bool
    :returns: Resolved configuration mapping.
    """
    file_path = Path(path)
    config = load_config(file_path)
    return resolve_config(
        config,
        file_path=str(file_path),
        cache=cache,
        transient=transient,
    )


if __name__ == "__main__":
    pass
