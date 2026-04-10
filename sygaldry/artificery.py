from __future__ import annotations

__author__ = "Rohan B. Dalton"

import inspect
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .cache import Instances
from .errors import (
    CircularReferenceError,
    ConfigReferenceError,
    ConstructorError,
    ImportResolutionError,
    ResolutionError,
    ValidationError,
)
from .loader import (
    _MISSING,
    _deep_merge,
    _get_by_path,
    _interpolate_config,
    _load_with_includes,
    _maybe_download,
    load_config,
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
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    instance: str | None


@dataclass(frozen=True)
class Node:
    """
    Intermediate node representation for optional IR usage.
    """

    name: str
    children: tuple[str, ...]
    bindings: dict[str, Any]


def _set_by_path(data: dict[str, Any], dotted_path: str, value: Any) -> None:
    """
    Set a nested value by dotted path, creating intermediate dicts.

    :param data: Root mapping to modify in-place.
    :param dotted_path: Dotted key path (e.g. ``"db.host"``).
    :param value: Value to set.
    :type data: dict
    :type dotted_path: str
    :type value: object
    """
    segments = dotted_path.split(".")
    current = data
    for segment in segments[:-1]:
        if segment not in current or not isinstance(current[segment], dict):
            current[segment] = dict()
        current = current[segment]
    current[segments[-1]] = value


def load_config_file(path: str | Path) -> dict[str, Any]:
    """
    Load a config file without resolving components.

    :param path: Path to a YAML or TOML config file, or an HTTP(S) URL.
    :type path: str | pathlib.Path
    :returns: Parsed and interpolated mapping.
    :rtype: dict[str, Any]
    """
    return load_config(path)


class ArtificeryLoader:
    """
    Lightweight loader wrapper for config files.
    """

    def __init__(self, path: str | Path) -> None:
        """
        Initialize the loader.

        :param path: Path to a YAML or TOML config file, or an HTTP(S) URL.
        :type path: str | pathlib.Path
        """
        self._path = path

    def load(self) -> dict[str, Any]:
        """
        Load and return the config mapping.

        :returns: Parsed and interpolated configuration mapping.
        :rtype: dict[str, Any]
        """
        return load_config(self._path)


def resolve_config(
    config: dict[str, Any],
    *,
    file_path: str | None = None,
    cache: Instances | None = None,
    transient: bool = False,
) -> dict[str, Any]:
    """
    Resolve a config mapping into an instantiated object graph.

    :param config: Configuration mapping.
    :param file_path: Source config path for context.
    :param cache: Optional instance cache.
    :param transient: If True, bypass caching.
    :type config: dict[str, Any]
    :type file_path: str | None
    :type cache: Instances | None
    :type transient: bool
    :returns: Resolved configuration mapping.
    :rtype: dict[str, Any]
    """

    artificery = Artificery(config=config, source=file_path, cache=cache, transient=transient)
    resolved = artificery.resolve()
    return resolved


class Artificery:
    """
    Component factory that loads, merges, and resolves config into objects.
    """

    def __init__(
        self,
        *paths: str | Path,
        config: dict[str, Any] | None = None,
        source: str | None = None,
        overrides: dict[str, Any] | None = None,
        uses: dict[str, str] | None = None,
        cache: Instances | None = None,
        transient: bool = False,
    ) -> None:
        """
        Initialize the Artificery.

        :param paths: Config file paths to load and deep-merge in order.
        :param config: Pre-loaded configuration mapping.
        :param source: Label for error messages (auto-derived from paths if omitted).
        :param overrides: Dotted-path overrides applied after merging, before interpolation.
        :param uses: Dotted-path mappings (target -> source) copied within the merged config.
        :param cache: Optional instance cache.
        :param transient: If True, bypass caching.
        :type paths: str | pathlib.Path
        :type config: dict | None
        :type source: str | None
        :type overrides: dict[str, Any] | None
        :type uses: dict[str, str] | None
        :type cache: Instances | None
        :type transient: bool
        :raises ValueError: If no config source is provided.
        """
        if not paths and config is None:
            raise ValueError("Artificery requires at least one path or a config dict.")

        self._active_config: dict[str, Any] = dict()
        self._cache = cache or Instances()
        self._overrides = overrides or dict()
        self._paths = tuple(path if isinstance(path, str) else Path(path) for path in paths)
        self._prepared: dict[str, Any] | None = None
        self._raw_config = config
        self._resolved_top: dict[str, Any] = dict()
        self._resolving_top: list[str] = list()
        self._source = source
        self._uses = uses or dict()
        self._transient = transient

    @property
    def config(self) -> dict[str, Any]:
        """
        The loaded, merged, and interpolated configuration (before resolution).

        :returns: Prepared configuration mapping.
        :rtype: dict[str, Any]
        """
        if not self._prepared:
            self._prepared = self._prepare()
        return self._prepared

    @property
    def _source_label(self) -> str | None:
        """
        Derive a source label for error messages.
        """
        if self._source is not None:
            return self._source
        elif self._paths:
            return str(self._paths[-1])
        else:
            return None

    def _prepare(self) -> dict[str, Any]:
        """
        Load, merge, apply overrides, and interpolate the config.

        :returns: Prepared configuration mapping.
        :rtype: dict[str, Any]
        """
        if self._paths:
            merged = self._load_and_merge()
            if self._raw_config is not None:
                merged = _deep_merge(merged, self._raw_config)
            merged = self._apply_uses(merged)
            merged = self._apply_overrides(merged)
            return _interpolate_config(merged, file_path=self._source_label)
        elif self._raw_config is not None:
            return self._raw_config
        else:
            raise ValueError("Artificery has no config source.")

    def _load_and_merge(self) -> dict[str, Any]:
        """
        Load multiple config files and deep-merge in order.

        :returns: Merged raw config mapping.
        :rtype: dict[str, Any]
        """
        merged: dict[str, Any] = dict()
        for path in self._paths:
            local = _maybe_download(path)
            resolved_path = local.expanduser().resolve()
            visited: set[Path] = set()
            data = _load_with_includes(resolved_path, ancestors=[], visited=visited)
            merged = _deep_merge(merged, data)
        return merged

    def _apply_uses(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Copy values within the config for each use mapping.

        :param config: Merged raw config.
        :type config: dict[str, Any]
        :returns: Modified config.
        :rtype: dict[str, Any]
        """
        for target_path, source_path in self._uses.items():
            value = _get_by_path(config, source_path)
            if value is _MISSING:
                available = sorted(config.keys())
                raise ConfigReferenceError(
                    f"Use source '{source_path}' not found. "
                    f"Available top-level keys: {available}",
                    file_path=self._source_label,
                    config_path=target_path,
                )
            _set_by_path(config, target_path, value)
        return config

    def _apply_overrides(self, config: dict[str, Any]) -> dict[str, Any]:
        """
        Apply dotted-path overrides to the config.

        :param config: Merged raw config.
        :type config: dict[str, Any]
        :returns: Modified config.
        :rtype: dict[str, Any]
        """
        for key, value in self._overrides.items():
            _set_by_path(config, key, value)
        return config

    def resolve(self) -> dict[str, Any]:
        """
        Validate and resolve the full config mapping into objects.

        :returns: Resolved configuration mapping.
        :rtype: dict[str, Any]
        """
        active = self.config
        self._active_config = active
        self._resolved_top: dict[str, Any] = dict()
        self._resolving_top: list[str] = list()
        self._validate_schema(active, path=[])
        self._validate_refs(active)
        return self._resolve_value(active, path=[])

    def _validate_schema(self, value: Any, *, path: list[str]) -> None:
        """
        Validate schema rules for reserved keys.

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
                    file_path=self._source_label,
                    config_path=".".join(path),
                )
            elif "_type" in value and "_func" in value:
                raise ValidationError(
                    "_type and _func are mutually exclusive.",
                    file_path=self._source_label,
                    config_path=".".join(path),
                )
            elif "_instance" in value and "_type" not in value:
                raise ValidationError(
                    "_instance is only valid with _type.",
                    file_path=self._source_label,
                    config_path=".".join(path),
                )

            for key, child in value.items():
                next_path = path + [str(key)]
                self._validate_schema(child, path=next_path)

        elif isinstance(value, list) or isinstance(value, tuple):
            for idx, child in enumerate(value):
                self._validate_schema(child, path=path + [str(idx)])

    def _validate_refs(self, config: dict[str, Any]) -> None:
        """
        Validate that all _ref targets exist in the config tree.

        For plain config paths (no ``_type`` at intermediate levels),
        validates the full dotted path through the raw config dicts.
        Stops validation at dict boundaries since deeper segments
        may be attribute accesses on constructed objects.

        :param config: Configuration mapping.
        :type config: dict[str, Any]
        :raises ConfigReferenceError: If any target is missing.
        """
        for ref_path, ref_key in _collect_refs(config):
            top = ref_key.split(".", 1)[0]
            if top not in config:
                raise ConfigReferenceError(
                    f"Reference target '{ref_key}' not found.",
                    file_path=self._source_label,
                    config_path=ref_path,
                )
            current = config[top]
            segments = ref_key.split(".")[1:]
            checked = top
            for segment in segments:
                if not isinstance(current, dict) or "_type" in current or "_func" in current:
                    break
                elif segment not in current:
                    raise ConfigReferenceError(
                        f"Reference target '{ref_key}' not found "
                        f"('{segment}' missing under '{checked}').",
                        file_path=self._source_label,
                        config_path=ref_path,
                    )
                else:
                    current = current[segment]
                    checked = f"{checked}.{segment}"

    def _resolve_value(self, value: Any, *, path: list[str]) -> Any:
        """
        Resolve any value recursively.

        :param value: Value to resolve.
        :param path: Dotted path context.
        :type value: object
        :type path: list[str]
        :returns: Resolved value.
        :rtype: object
        """
        if isinstance(value, dict):
            return self._resolve_dict(value, path=path)
        elif isinstance(value, list):
            return [
                self._resolve_value(item, path=path + [str(idx)])
                for idx, item in enumerate(value)
            ]
        elif isinstance(value, tuple):
            return tuple(
                self._resolve_value(item, path=path + [str(idx)])
                for idx, item in enumerate(value)
            )
        else:
            return value

    def _resolve_dict(self, value: dict[str, Any], *, path: list[str]) -> Any:
        """
        Resolve a dict, applying reserved-key rules.

        :param value: Mapping to resolve.
        :param path: Dotted path context.
        :type value: dict[str, Any]
        :type path: list[str]
        :returns: Resolved mapping or constructed object.
        :rtype: object
        """
        if "_ref" in value:
            return self._resolve_ref(value["_ref"], path)
        elif "_type" in value:
            return self._resolve_type(value, path)
        elif "_func" in value:
            return self._resolve_func(value, path)
        elif value.get("_deep") is False:
            return {k: v for k, v in value.items() if k != "_deep"}
        elif "_entries" in value:
            return self._resolve_entries(value, path)
        else:
            resolved: dict[str, Any] = dict()
            for key, child in value.items():
                resolved[key] = self._resolve_value(child, path=path + [str(key)])
            return resolved

    def _resolve_ref(self, ref: Any, path: list[str]) -> Any:
        """
        Resolve a ``_ref`` mapping.

        :param ref: Reference value.
        :param path: Dotted path context.
        :type ref: object
        :type path: list[str]
        :returns: Resolved referenced object or attribute.
        :rtype: object
        :raises ConfigReferenceError: If the ref is invalid or missing.
        """
        if not isinstance(ref, str) or not ref:
            raise ConfigReferenceError(
                "_ref must be a non-empty string.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        else:
            top, _, remainder = ref.partition(".")
            target = self._resolve_top_level(top, path)
            if remainder:
                for attr in remainder.split("."):
                    try:
                        target = getattr(target, attr)
                    except AttributeError as exc:
                        raise ConfigReferenceError(
                            f"Attribute '{attr}' not found on reference '{top}'.",
                            file_path=self._source_label,
                            config_path=".".join(path),
                        ) from exc
            return target

    def _resolve_top_level(self, key: str, path: list[str]) -> Any:
        """
        Resolve a top-level config entry, with cycle detection.

        :param key: Top-level key to resolve.
        :param path: Dotted path context.
        :type key: str
        :type path: list[str]
        :returns: Resolved value.
        :rtype: object
        :raises CircularReferenceError: If a cycle is detected.
        """
        if key in self._resolved_top:
            return self._resolved_top[key]
        elif key in self._resolving_top:
            chain = " -> ".join(self._resolving_top + [key])
            raise CircularReferenceError(
                f"Circular reference detected: {chain}",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        elif key not in self._active_config:
            raise ConfigReferenceError(
                f"Reference target '{key}' not found.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        else:
            self._resolving_top.append(key)
            resolved = self._resolve_value(self._active_config[key], path=[key])
            self._resolving_top.pop()
            self._resolved_top[key] = resolved
            return resolved

    def _resolve_entries(self, value: dict[str, Any], path: list[str]) -> dict[Any, Any]:
        """
        Resolve a mapping encoded via ``_entries``.

        :param value: Mapping containing ``_entries`` list.
        :param path: Dotted path context.
        :type value: dict[str, Any]
        :type path: list[str]
        :returns: Resolved mapping.
        :rtype: dict[Any, Any]
        :raises ResolutionError: If entries are malformed.
        """
        entries = value.get("_entries")
        if not isinstance(entries, list):
            raise ResolutionError(
                "_entries must be a list.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        elif len(value.keys() - {"_entries"}) != 0:
            raise ResolutionError(
                "_entries cannot be combined with other keys.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        else:
            resolved: dict[Any, Any] = dict()
            for idx, entry in enumerate(entries):
                if not isinstance(entry, dict) or "_key" not in entry or "_value" not in entry:
                    raise ResolutionError(
                        "Each _entries item must contain _key and _value.",
                        file_path=self._source_label,
                        config_path=".".join(path + [str(idx)]),
                    )
                key = self._resolve_value(entry["_key"], path=path + [str(idx), "_key"])
                val = self._resolve_value(entry["_value"], path=path + [str(idx), "_value"])
                try:
                    hash(key)
                except Exception as exc:
                    raise ResolutionError(
                        "Resolved _entries keys must be hashable.",
                        file_path=self._source_label,
                        config_path=".".join(path + [str(idx), "_key"]),
                    ) from exc

                if key in resolved:
                    raise ResolutionError(
                        f"Duplicate _entries key '{key}'.",
                        file_path=self._source_label,
                        config_path=".".join(path + [str(idx), "_key"]),
                    )
                else:
                    resolved[key] = val
            return resolved

    def _resolve_func(self, value: dict[str, Any], path: list[str]) -> Any:
        """
        Resolve a ``_func`` mapping to a callable.

        :param value: Mapping containing ``_func``.
        :param path: Dotted path context.
        :type value: dict[str, Any]
        :type path: list[str]
        :returns: Imported callable.
        :rtype: object
        :raises ValidationError: If extra keys accompany ``_func``.
        """
        extras = set(value) - {"_func"}
        if extras:
            raise ValidationError(
                f"_func does not accept other keys, found: {sorted(extras)}.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        else:
            func_path = value.get("_func")
            try:
                return import_dotted_path(
                    func_path,
                    file_path=self._source_label,
                    config_path=".".join(path),
                )
            except ImportResolutionError:
                raise

    def _resolve_type(self, value: dict[str, Any], path: list[str]) -> Any:
        """
        Resolve a ``_type`` mapping into an instance.

        :param value: Mapping containing ``_type`` and constructor data.
        :param path: Dotted path context.
        :type value: dict[str, Any]
        :type path: list[str]
        :returns: Constructed instance (possibly cached).
        :rtype: object
        """
        type_path = value.get("_type")
        args = value.get("_args", [])
        extra_kwargs = value.get("_kwargs", {})
        instance = value.get("_instance")
        if not isinstance(args, list):
            raise ResolutionError(
                "_args must be a list.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        elif not isinstance(extra_kwargs, dict):
            raise ResolutionError(
                "_kwargs must be a mapping.",
                file_path=self._source_label,
                config_path=".".join(path),
            )
        else:
            kwargs = {k: v for k, v in value.items() if k not in RESERVED_KEYS}
            resolved_args = tuple(
                self._resolve_value(arg, path=path + ["_args"]) for arg in args
            )
            resolved_kwargs = {
                key: self._resolve_value(val, path=path + [key]) for key, val in kwargs.items()
            }
            for key, val in extra_kwargs.items():
                resolved_kwargs[key] = self._resolve_value(val, path=path + ["_kwargs", key])

            target = import_dotted_path(
                type_path,
                file_path=self._source_label,
                config_path=".".join(path),
            )

            resolved_kwargs = _validate_signature(
                target,
                resolved_args,
                resolved_kwargs,
                file_path=self._source_label,
                config_path=".".join(path),
            )

            def factory() -> Any:
                try:
                    return target(*resolved_args, **resolved_kwargs)
                except Exception as exc:  # noqa: BLE001
                    raise ConstructorError(
                        f"Failed to construct '{type_path}'.",
                        file_path=self._source_label,
                        config_path=".".join(path),
                    ) from exc

        instance = self._cache.get_or_create(
            type_path,
            instance,
            resolved_args,
            resolved_kwargs,
            factory,
            transient=self._transient,
            file_path=self._source_label,
            config_path=".".join(path),
        )
        return instance


def _collect_refs(value: Any, *, path: list[str] | None = None) -> Iterable[tuple[str, str]]:
    """
    Collect ``_ref`` occurrences from a config tree.

    :param value: Root value to inspect.
    :param path: Current path stack.
    :type value: object
    :type path: list[str] | None
    :returns: Iterable of (config_path, ref_target) pairs.
    :rtype: collections.abc.Iterable[tuple[str, str]]
    """
    path = path or list()
    if isinstance(value, dict):
        if "_ref" in value:
            yield ".".join(path), value["_ref"]
            return
        else:
            for key, child in value.items():
                yield from _collect_refs(child, path=path + [str(key)])
    elif isinstance(value, list) or isinstance(value, tuple):
        for idx, child in enumerate(value):
            yield from _collect_refs(child, path=path + [str(idx)])


def _validate_signature(
    target: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    file_path: str | None,
    config_path: str,
) -> dict[str, Any]:
    """
    Validate constructor signature and filter extra kwargs.

    :param target: Callable to validate.
    :param args: Positional arguments.
    :param kwargs: Keyword arguments.
    :param file_path: Source config path for context.
    :param config_path: Dotted config path for context.
    :type target: object
    :type args: tuple[Any, ...]
    :type kwargs: dict[str, Any]
    :type file_path: str | None
    :type config_path: str
    :returns: Possibly filtered kwargs.
    :rtype: dict[str, Any]
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

    missing = list()
    for name, param in signature.parameters.items():
        if (
            param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
            or param.default is not param.empty
        ):
            continue
        elif name not in bound.arguments:
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
