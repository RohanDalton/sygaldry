"""
Config resolver for component instantiation.
"""

from __future__ import annotations

__author__ = "Rohan B. Dalton"

import inspect
import warnings
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .cache import Instances
from .errors import (
    CircularReferenceError,
    ConfigReferenceError,
    ConstructorError,
    ImportResolutionError,
    ResolutionError,
    ValidationError,
)
from .types import RESERVED_KEYS, import_dotted_path


@dataclass(frozen=True)
class Reference:
    """
    Reference to a dotted config path.
    """

    path: str


@dataclass(frozen=True)
class ConstructorSpec:
    """
    Constructor specification for a component.
    """

    target: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    instance: Optional[str]


@dataclass(frozen=True)
class Node:
    """
    Intermediate node representation for optional IR usage.
    """

    name: str
    children: Tuple[str, ...]
    bindings: Dict[str, Any]


def resolve_config(
    config: Dict[str, Any],
    *,
    file_path: Optional[str] = None,
    cache: Optional[Instances] = None,
    transient: bool = False,
) -> Dict[str, Any]:
    """Resolve a config mapping into an instantiated object graph.

    :param config: Configuration mapping.
    :param file_path: Source config path for context.
    :param cache: Optional instance cache.
    :param transient: If True, bypass caching.
    :type config: dict
    :type file_path: str | None
    :type cache: Instances | None
    :type transient: bool
    :returns: Resolved configuration mapping.
    """
    resolver = _Resolver(config, file_path=file_path, cache=cache, transient=transient)
    return resolver.resolve()


class _Resolver:
    """
    Resolver that walks and instantiates config values.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        file_path: Optional[str],
        cache: Optional[Instances],
        transient: bool,
    ) -> None:
        """Initialize the resolver.

        :param config: Configuration mapping.
        :param file_path: Source config path for context.
        :param cache: Optional instance cache.
        :param transient: If True, bypass caching.
        :type config: dict
        :type file_path: str | None
        :type cache: Instances | None
        :type transient: bool
        """
        self._config = config
        self._file_path = file_path
        self._cache = cache or Instances()
        self._transient = transient
        self._resolved_top: Dict[str, Any] = {}
        self._resolving_top: List[str] = []

    def resolve(self) -> Dict[str, Any]:
        """
        Validate and resolve the full config mapping.
        """
        self._validate_schema(self._config, path=[])
        self._validate_refs(self._config)
        return self._resolve_value(self._config, path=[])

    def _validate_schema(self, value: Any, *, path: List[str]) -> None:
        """Validate schema rules for reserved keys.

        :param value: Value to validate.
        :param path: Dotted path context.
        :type value: object
        :type path: list[str]
        :raises ValidationError: On schema violations.
        """
        if isinstance(value, dict):
            if "_ref" in value and len(value) != 1:
                raise ValidationError(
                    "_ref must be the only key in its mapping.",
                    file_path=self._file_path,
                    config_path=".".join(path),
                )
            if "_type" in value and "_func" in value:
                raise ValidationError(
                    "_type and _func are mutually exclusive.",
                    file_path=self._file_path,
                    config_path=".".join(path),
                )
            if "_instance" in value and "_type" not in value:
                raise ValidationError(
                    "_instance is only valid with _type.",
                    file_path=self._file_path,
                    config_path=".".join(path),
                )
            for key, child in value.items():
                next_path = path + [str(key)]
                self._validate_schema(child, path=next_path)
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                self._validate_schema(child, path=path + [str(idx)])
        elif isinstance(value, tuple):
            for idx, child in enumerate(value):
                self._validate_schema(child, path=path + [str(idx)])

    def _validate_refs(self, config: Dict[str, Any]) -> None:
        """Validate that all _ref targets exist in the config tree.

        For plain config paths (no ``_type`` at intermediate levels),
        validates the full dotted path through the raw config dicts.
        Stops validation at dict boundaries since deeper segments
        may be attribute accesses on constructed objects.

        :param config: Configuration mapping.
        :type config: dict
        :raises ConfigReferenceError: If any target is missing.
        """
        for ref_path, ref_key in _collect_refs(config):
            top = ref_key.split(".", 1)[0]
            if top not in config:
                raise ConfigReferenceError(
                    f"Reference target '{ref_key}' not found.",
                    file_path=self._file_path,
                    config_path=ref_path,
                )
            current = config[top]
            segments = ref_key.split(".")[1:]
            checked = top
            for segment in segments:
                if not isinstance(current, dict):
                    break
                if "_type" in current or "_func" in current:
                    break
                if segment not in current:
                    raise ConfigReferenceError(
                        f"Reference target '{ref_key}' not found "
                        f"('{segment}' missing under '{checked}').",
                        file_path=self._file_path,
                        config_path=ref_path,
                    )
                current = current[segment]
                checked = f"{checked}.{segment}"

    def _resolve_value(self, value: Any, *, path: List[str]) -> Any:
        """Resolve any value recursively.

        :param value: Value to resolve.
        :param path: Dotted path context.
        :type value: object
        :type path: list[str]
        :returns: Resolved value.
        """
        if isinstance(value, dict):
            return self._resolve_dict(value, path=path)
        if isinstance(value, list):
            return [
                self._resolve_value(item, path=path + [str(idx)])
                for idx, item in enumerate(value)
            ]
        if isinstance(value, tuple):
            return tuple(
                self._resolve_value(item, path=path + [str(idx)])
                for idx, item in enumerate(value)
            )
        return value

    def _resolve_dict(self, value: Dict[str, Any], *, path: List[str]) -> Any:
        """Resolve a dict, applying reserved-key rules.

        :param value: Mapping to resolve.
        :param path: Dotted path context.
        :type value: dict
        :type path: list[str]
        :returns: Resolved mapping or constructed object.
        """
        if "_ref" in value:
            return self._resolve_ref(value["_ref"], path)
        if "_type" in value:
            return self._resolve_type(value, path)
        if "_func" in value:
            return self._resolve_func(value, path)
        if value.get("_deep") is False:
            return {k: v for k, v in value.items() if k != "_deep"}
        if "_entries" in value:
            return self._resolve_entries(value, path)

        resolved: Dict[str, Any] = {}
        for key, child in value.items():
            resolved[key] = self._resolve_value(child, path=path + [str(key)])
        return resolved

    def _resolve_ref(self, ref: Any, path: List[str]) -> Any:
        """Resolve a ``_ref`` mapping.

        :param ref: Reference value.
        :param path: Dotted path context.
        :type ref: object
        :type path: list[str]
        :returns: Resolved referenced object or attribute.
        :raises ConfigReferenceError: If the ref is invalid or missing.
        """
        if not isinstance(ref, str) or not ref:
            raise ConfigReferenceError(
                "_ref must be a non-empty string.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        top, _, remainder = ref.partition(".")
        target = self._resolve_top_level(top, path)
        if remainder:
            for attr in remainder.split("."):
                try:
                    target = getattr(target, attr)
                except AttributeError as exc:
                    raise ConfigReferenceError(
                        f"Attribute '{attr}' not found on reference '{top}'.",
                        file_path=self._file_path,
                        config_path=".".join(path),
                    ) from exc
        return target

    def _resolve_top_level(self, key: str, path: List[str]) -> Any:
        """Resolve a top-level config entry, with cycle detection.

        :param key: Top-level key to resolve.
        :param path: Dotted path context.
        :type key: str
        :type path: list[str]
        :returns: Resolved value.
        :raises CircularReferenceError: If a cycle is detected.
        """
        if key in self._resolved_top:
            return self._resolved_top[key]
        if key in self._resolving_top:
            chain = " -> ".join(self._resolving_top + [key])
            raise CircularReferenceError(
                f"Circular reference detected: {chain}",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        if key not in self._config:
            raise ConfigReferenceError(
                f"Reference target '{key}' not found.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        self._resolving_top.append(key)
        resolved = self._resolve_value(self._config[key], path=[key])
        self._resolving_top.pop()
        self._resolved_top[key] = resolved
        return resolved

    def _resolve_entries(self, value: Dict[str, Any], path: List[str]) -> Dict[Any, Any]:
        """Resolve a mapping encoded via ``_entries``.

        :param value: Mapping containing ``_entries`` list.
        :param path: Dotted path context.
        :type value: dict
        :type path: list[str]
        :returns: Resolved mapping.
        :raises ResolutionError: If entries are malformed.
        """
        entries = value.get("_entries")
        if not isinstance(entries, list):
            raise ResolutionError(
                "_entries must be a list.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        if len(value.keys() - {"_entries"}) != 0:
            raise ResolutionError(
                "_entries cannot be combined with other keys.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        resolved: Dict[Any, Any] = {}
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict) or "_key" not in entry or "_value" not in entry:
                raise ResolutionError(
                    "Each _entries item must contain _key and _value.",
                    file_path=self._file_path,
                    config_path=".".join(path + [str(idx)]),
                )
            key = self._resolve_value(entry["_key"], path=path + [str(idx), "_key"])
            val = self._resolve_value(entry["_value"], path=path + [str(idx), "_value"])
            try:
                hash(key)
            except Exception as exc:
                raise ResolutionError(
                    "Resolved _entries keys must be hashable.",
                    file_path=self._file_path,
                    config_path=".".join(path + [str(idx), "_key"]),
                ) from exc
            if key in resolved:
                raise ResolutionError(
                    f"Duplicate _entries key '{key}'.",
                    file_path=self._file_path,
                    config_path=".".join(path + [str(idx), "_key"]),
                )
            resolved[key] = val
        return resolved

    def _resolve_func(self, value: Dict[str, Any], path: List[str]) -> Any:
        """Resolve a ``_func`` mapping to a callable.

        :param value: Mapping containing ``_func``.
        :param path: Dotted path context.
        :type value: dict
        :type path: list[str]
        :returns: Imported callable.
        :raises ValidationError: If extra keys accompany ``_func``.
        """
        extras = set(value) - {"_func"}
        if extras:
            raise ValidationError(
                f"_func does not accept other keys, found: {sorted(extras)}.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        func_path = value.get("_func")
        try:
            return import_dotted_path(
                func_path,
                file_path=self._file_path,
                config_path=".".join(path),
            )
        except ImportResolutionError:
            raise

    def _resolve_type(self, value: Dict[str, Any], path: List[str]) -> Any:
        """Resolve a ``_type`` mapping into an instance.

        :param value: Mapping containing ``_type`` and constructor data.
        :param path: Dotted path context.
        :type value: dict
        :type path: list[str]
        :returns: Constructed instance (possibly cached).
        """
        type_path = value.get("_type")
        args = value.get("_args", [])
        instance = value.get("_instance")
        if not isinstance(args, list):
            raise ResolutionError(
                "_args must be a list.",
                file_path=self._file_path,
                config_path=".".join(path),
            )

        kwargs = {k: v for k, v in value.items() if k not in RESERVED_KEYS}
        resolved_args = tuple(self._resolve_value(arg, path=path + ["_args"]) for arg in args)
        resolved_kwargs = {
            key: self._resolve_value(val, path=path + [key]) for key, val in kwargs.items()
        }

        try:
            target = import_dotted_path(
                type_path,
                file_path=self._file_path,
                config_path=".".join(path),
            )
        except ImportResolutionError:
            raise

        resolved_kwargs = _validate_signature(
            target,
            resolved_args,
            resolved_kwargs,
            file_path=self._file_path,
            config_path=".".join(path),
        )

        def factory() -> Any:
            try:
                return target(*resolved_args, **resolved_kwargs)
            except Exception as exc:  # noqa: BLE001
                raise ConstructorError(
                    f"Failed to construct '{type_path}'.",
                    file_path=self._file_path,
                    config_path=".".join(path),
                ) from exc

        return self._cache.get_or_create(
            type_path,
            instance,
            resolved_args,
            resolved_kwargs,
            factory,
            transient=self._transient,
            file_path=self._file_path,
            config_path=".".join(path),
        )


def _collect_refs(
    value: Any, *, path: Optional[List[str]] = None
) -> Iterable[Tuple[str, str]]:
    """Collect ``_ref`` occurrences from a config tree.

    :param value: Root value to inspect.
    :param path: Current path stack.
    :type value: object
    :type path: list[str] | None
    :returns: Iterable of (config_path, ref_target) pairs.
    """
    if path is None:
        path = []
    if isinstance(value, dict):
        if "_ref" in value:
            yield (".".join(path), value["_ref"])
            return
        for key, child in value.items():
            yield from _collect_refs(child, path=path + [str(key)])
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            yield from _collect_refs(child, path=path + [str(idx)])
    elif isinstance(value, tuple):
        for idx, child in enumerate(value):
            yield from _collect_refs(child, path=path + [str(idx)])


def _validate_signature(
    target: Any,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    *,
    file_path: Optional[str],
    config_path: str,
) -> Dict[str, Any]:
    """Validate constructor signature and filter extra kwargs.

    :param target: Callable to validate.
    :param args: Positional arguments.
    :param kwargs: Keyword arguments.
    :param file_path: Source config path for context.
    :param config_path: Dotted config path for context.
    :type target: object
    :type args: tuple
    :type kwargs: dict
    :type file_path: str | None
    :type config_path: str
    :returns: Possibly filtered kwargs.
    :raises ConstructorError: If required parameters are missing.
    """
    try:
        signature = inspect.signature(target)
    except (TypeError, ValueError):
        return kwargs

    has_var_kw = any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values())
    if not has_var_kw:
        allowed = {
            name
            for name, param in signature.parameters.items()
            if param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
        }
        extras = set(kwargs) - allowed
        if extras:
            warnings.warn(
                f"Extra kwargs for '{getattr(target, '__name__', target)}': {sorted(extras)}",
                RuntimeWarning,
                stacklevel=2,
            )
            kwargs = {k: v for k, v in kwargs.items() if k not in extras}

    try:
        bound = signature.bind_partial(*args, **kwargs)
    except TypeError as exc:
        raise ConstructorError(
            f"Constructor signature mismatch for '{getattr(target, '__name__', target)}': {exc}.",
            file_path=file_path,
            config_path=config_path,
        ) from exc

    missing = []
    for name, param in signature.parameters.items():
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue
        if param.default is not param.empty:
            continue
        if name not in bound.arguments:
            missing.append(name)

    if missing:
        raise ConstructorError(
            f"Missing required parameters: {missing}.",
            file_path=file_path,
            config_path=config_path,
        )
    return kwargs


if __name__ == "__main__":
    pass
