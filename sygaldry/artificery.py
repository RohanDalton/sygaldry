"""
Artificery factory conveniences.
"""

from __future__ import annotations

__author__ = "Rohan B. Dalton"

from pathlib import Path
from typing import Any, Dict, Optional

from .cache import Instances
from .loader import load_config
from .resolver import resolve_config


def load_config_file(path: str | Path) -> Dict[str, Any]:
    """
    Load a config file without resolving components.

    :param path: Path to a YAML or TOML config file.
    :type path: str | pathlib.Path
    :returns: Parsed and interpolated mapping.
    """
    file_path = Path(path)
    return load_config(file_path)


class ArtificeryLoader:
    """
    Lightweight loader wrapper for config files.
    """

    def __init__(self, path: str | Path) -> None:
        """
        Initialize the loader.

        :param path: Path to a YAML or TOML config file.
        :type path: str | pathlib.Path
        """
        self._path = Path(path)

    def load(self) -> Dict[str, Any]:
        """
        Load and return the config mapping.
        """
        return load_config(self._path)


class Artificery:
    """
    Component factory that resolves a config into objects.
    """

    def __init__(
        self,
        file_path: str | Path | None = None,
        *,
        config: Optional[Dict[str, Any]] = None,
        cache: Optional[Instances] = None,
        transient: bool = False,
    ) -> None:
        """
        Initialize an Artificery instance.

        :param file_path: Path to a config file.
        :param config: Pre-loaded config mapping.
        :param cache: Optional instance cache.
        :param transient: If True, bypass caching.
        :type file_path: str | pathlib.Path | None
        :type config: dict | None
        :type cache: Instances | None
        :type transient: bool
        :raises ValueError: If no config source is provided.
        """
        if file_path is None and config is None:
            raise ValueError("Artificery requires file_path or config.")
        self._file_path = Path(file_path) if file_path is not None else None
        self._config = config
        self._cache = cache or Instances()
        self._transient = transient

    def resolve(self) -> Dict[str, Any]:
        """
        Resolve the configured mapping to an object graph.

        :returns: Resolved configuration mapping.
        :raises ValueError: If no config source is available.
        """
        if self._config is None:
            if self._file_path is None:
                raise ValueError("Artificery has no config source.")
            self._config = load_config(self._file_path)
        return resolve_config(
            self._config,
            file_path=str(self._file_path) if self._file_path is not None else None,
            cache=self._cache,
            transient=self._transient,
        )


if __name__ == "__main__":
    pass
