"""
Instance cache with hash conflict detection.
"""

from __future__ import annotations

__author__ = "Rohan B. Dalton"

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .errors import ConfigConflictError

_NOT_FOUND = object()


def _normalize_for_hash(value: Any, *, _memo: dict[int, str] | None = None) -> Any:
    """
    Normalize values into JSON-serializable structures for hashing.

    :param value: Value to normalize.
    :type value: object
    :returns: JSON-serializable structure.
    :rtype: object
    """
    _memo = _memo or dict()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    elif isinstance(value, Path):
        return {"__path__": str(value)}
    elif isinstance(value, bytes):
        return {"__bytes__": value.hex()}
    elif isinstance(value, (list, tuple)):
        return [_normalize_for_hash(item, _memo=_memo) for item in value]
    elif isinstance(value, dict):
        entries = list()
        for key, val in value.items():
            normalized_key = _normalize_for_hash(key, _memo=_memo)
            normalized_value = _normalize_for_hash(val, _memo=_memo)
            entries.append((normalized_key, normalized_value))

        entries.sort(
            key=lambda pair: json.dumps(
                pair[0],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        )
        return {"__dict__": [[key, value] for key, value in entries]}

    elif isinstance(value, set):
        items = [_normalize_for_hash(item, _memo=_memo) for item in value]
        items.sort(
            key=lambda item: json.dumps(
                item,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        )
        return {"__set__": items}
    else:
        object_id = id(value)
        token = _memo.get(object_id)
        if token is None:
            module = value.__class__.__module__
            name = value.__class__.__qualname__
            token = f"{module}.{name}@{object_id}"
            _memo[object_id] = token
        return {"__object__": token}


def _canonical_hash(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    """
    Compute a canonical hash for args/kwargs.

    :param args: Positional arguments for constructor.
    :param kwargs: Keyword arguments for constructor.
    :type args: tuple[Any, ...]
    :type kwargs: dict[str, Any]
    :returns: SHA-256 hash of canonical JSON payload.
    :rtype: str
    :raises ConfigConflictError: If the payload is not JSON-serializable.
    """
    payload = _normalize_for_hash({"args": args, "kwargs": kwargs})
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CacheEntry:
    """
    Cached instance entry with hash for conflict detection.
    """

    value: Any
    spec_hash: str


class Instances:
    """
    Per-factory cache keyed by (type_path, instance tag or spec hash).
    """

    def __init__(self) -> None:
        """
        Initialize an empty cache.
        """
        self._entries: dict[tuple[str, str | None, str | None], CacheEntry] = dict()

    @staticmethod
    def _cache_key(
        type_path: str,
        instance: str | None,
        spec_hash: str | None,
    ) -> tuple[str, str | None, str | None]:
        if instance is None:
            return type_path, None, spec_hash
        return type_path, instance, None

    def get(
        self,
        type_path: str,
        instance: str | None,
        *,
        expected_hash: str | None = None,
        file_path: str | None = None,
        config_path: str | None = None,
    ) -> Any:
        """
        Return a cached instance if present.

        :param type_path: Dotted type path used as cache key.
        :param instance: Optional instance tag.
        :param expected_hash: Optional hash to validate cache entry.
        :param file_path: Source config file path, if known.
        :param config_path: Dotted config path for context.
        :type type_path: str
        :type instance: str | None
        :type expected_hash: str | None
        :type file_path: str | None
        :type config_path: str | None
        :returns: Cached instance if found, or ``_NOT_FOUND`` sentinel.
        :rtype: object
        :raises ConfigConflictError: If the cached hash conflicts.
        """
        if instance is None and expected_hash is None:
            return _NOT_FOUND
        key = self._cache_key(type_path, instance, expected_hash)
        entry = self._entries.get(key)
        if entry is None:
            return _NOT_FOUND
        if (
            instance is not None
            and expected_hash is not None
            and entry.spec_hash != expected_hash
        ):
            raise ConfigConflictError(
                f"Cache conflict for '{type_path}' with instance '{instance}'.",
                file_path=file_path,
                config_path=config_path,
            )
        return entry.value

    def set(
        self,
        type_path: str,
        instance: str | None,
        value: Any,
        *,
        spec_hash: str,
        file_path: str | None = None,
        config_path: str | None = None,
    ) -> Any:
        """
        Insert or validate a cache entry.

        :param type_path: Dotted type path used as cache key.
        :param instance: Optional instance tag.
        :param value: Resolved object instance.
        :param spec_hash: Hash for the constructor spec.
        :param file_path: Source config file path, if known.
        :param config_path: Dotted config path for context.
        :type type_path: str
        :type instance: str | None
        :type value: object
        :type spec_hash: str
        :type file_path: str | None
        :type config_path: str | None
        :returns: The inserted instance.
        :rtype: object
        :raises ConfigConflictError: If an existing entry conflicts.
        """
        key = self._cache_key(type_path, instance, spec_hash)
        entry = self._entries.get(key)
        if instance is not None and entry is not None and entry.spec_hash != spec_hash:
            raise ConfigConflictError(
                f"Cache conflict for '{type_path}' with instance '{instance}'.",
                file_path=file_path,
                config_path=config_path,
            )
        self._entries[key] = CacheEntry(value=value, spec_hash=spec_hash)
        return value

    def get_or_create(
        self,
        type_path: str,
        instance: str | None,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        factory: Callable[[], Any],
        *,
        transient: bool = False,
        file_path: str | None = None,
        config_path: str | None = None,
    ) -> Any:
        """
        Get or create a cached instance.

        :param type_path: Dotted type path used as cache key.
        :param instance: Optional instance tag.
        :param args: Resolved positional args.
        :param kwargs: Resolved keyword args.
        :param factory: Callable that constructs the instance.
        :param transient: If True, bypass caching.
        :param file_path: Source config file path, if known.
        :param config_path: Dotted config path for context.
        :type type_path: str
        :type instance: str | None
        :type args: tuple[Any, ...]
        :type kwargs: dict[str, Any]
        :type factory: collections.abc.Callable[[], Any]
        :type transient: bool
        :type file_path: str | None
        :type config_path: str | None
        :returns: Cached or newly created instance.
        :rtype: object
        """
        if transient:
            return factory()

        spec_hash = _canonical_hash(args, kwargs)
        existing = self.get(
            type_path,
            instance,
            expected_hash=spec_hash,
            file_path=file_path,
            config_path=config_path,
        )
        if existing is not _NOT_FOUND:
            return existing

        value = factory()
        return self.set(
            type_path,
            instance,
            value,
            spec_hash=spec_hash,
            file_path=file_path,
            config_path=config_path,
        )


if __name__ == "__main__":
    pass
