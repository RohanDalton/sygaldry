"""
Instance cache with hash conflict detection.
"""

from __future__ import annotations

__author__ = "Rohan B. Dalton"

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from .errors import ConfigConflictError

_NOT_FOUND = object()


def _normalize_for_hash(value: Any, *, _memo: Optional[Dict[int, str]] = None) -> Any:
    """Normalize values into JSON-serializable structures for hashing.

    :param value: Value to normalize.
    :type value: object
    :returns: JSON-serializable structure.
    """
    if _memo is None:
        _memo = {}

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, Path):
        return {"__path__": str(value)}

    if isinstance(value, bytes):
        return {"__bytes__": value.hex()}

    if isinstance(value, (list, tuple)):
        return [_normalize_for_hash(item, _memo=_memo) for item in value]

    if isinstance(value, dict):
        entries = list()
        for key, val in value.items():
            norm_key = _normalize_for_hash(key, _memo=_memo)
            norm_val = _normalize_for_hash(val, _memo=_memo)
            entries.append((norm_key, norm_val))
        entries.sort(
            key=lambda pair: json.dumps(
                pair[0],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            )
        )
        return {"__dict__": [[key, value] for key, value in entries]}

    if isinstance(value, set):
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

    obj_id = id(value)
    token = _memo.get(obj_id)
    if token is None:
        token = f"{value.__class__.__module__}.{value.__class__.__qualname__}@{obj_id}"
        _memo[obj_id] = token
    return {"__object__": token}


def _canonical_hash(args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> str:
    """Compute a canonical hash for args/kwargs.

    :param args: Positional arguments for constructor.
    :param kwargs: Keyword arguments for constructor.
    :type args: tuple
    :type kwargs: dict
    :returns: SHA-256 hash of canonical JSON payload.
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
        self._entries: Dict[Tuple[str, Optional[str], Optional[str]], CacheEntry] = {}

    @staticmethod
    def _cache_key(
        type_path: str,
        instance: Optional[str],
        spec_hash: Optional[str],
    ) -> Tuple[str, Optional[str], Optional[str]]:
        if instance is None:
            return (type_path, None, spec_hash)
        return (type_path, instance, None)

    def get(
        self,
        type_path: str,
        instance: Optional[str],
        *,
        expected_hash: Optional[str] = None,
        file_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> Any:
        """Return a cached instance if present.

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
        instance: Optional[str],
        value: Any,
        *,
        spec_hash: str,
        file_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> Any:
        """Insert or validate a cache entry.

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
        instance: Optional[str],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        factory: Callable[[], Any],
        *,
        transient: bool = False,
        file_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ) -> Any:
        """Get or create a cached instance.

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
        :type args: tuple
        :type kwargs: dict
        :type factory: collections.abc.Callable
        :type transient: bool
        :type file_path: str | None
        :type config_path: str | None
        :returns: Cached or newly created instance.
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
