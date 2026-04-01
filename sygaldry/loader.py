"""
Config loading with includes, deep merge, and interpolation.
"""

from __future__ import annotations

__author__ = "Rohan B. Dalton"

import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Optional

from .errors import (
    CircularIncludeError,
    CircularInterpolationError,
    IncludeError,
    InterpolationError,
    ParseError,
)

try:
    import tomllib  # type: ignore
except ImportError:  # pragma: no cover - fallback only
    import tomli as tomllib  # type: ignore

_INTEGER_RE = re.compile(r"^(?P<integer>[-+]?\d+)$")
_FLOAT_RE = re.compile(r"^(?P<float>[-+]?\d*\.\d+(?:[eE][-+]?\d+)?)$")
_SCI_INT_RE = re.compile(r"^(?P<sci_int>[-+]?\d+[eE][-+]?\d+)$")


def load_config(path: Path) -> dict[str, Any]:
    """
    Load and interpolate a config file.

    :param path: Path to a YAML or TOML config file.
    :type path: pathlib.Path
    :returns: Merged, interpolated configuration mapping.
    :rtype: dict[str, Any]
    """
    visited: set[Path] = set()
    data = _load_with_includes(path, ancestors=[], visited=visited)
    return _interpolate_config(data, file_path=str(path))


def _load_with_includes(
    path: Path, ancestors: list[Path], visited: set[Path]
) -> dict[str, Any]:
    """
    Load a file and recursively apply includes.

    Uses *ancestors* (the current include stack) for true cycle detection
    and *visited* (a global set) for diamond-include deduplication.

    :param path: Path to the config file.
    :param ancestors: Current include stack from root to parent.
    :param visited: Global set of already-loaded paths.
    :type path: pathlib.Path
    :type ancestors: list[pathlib.Path]
    :type visited: set[pathlib.Path]
    :returns: Merged configuration mapping.
    :rtype: dict[str, Any]
    :raises CircularIncludeError: If a circular include is detected.
    """
    path = path.expanduser().resolve()
    if path in ancestors:
        chain_display = " -> ".join(str(p) for p in ancestors + [path])
        raise CircularIncludeError(
            f"Circular include detected: {chain_display}", file_path=str(path)
        )

    if path in visited:
        return dict()

    visited.add(path)
    raw = _load_file(path)
    includes = raw.pop("_include", None)
    merged: dict[str, Any] = dict()
    child_ancestors = ancestors + [path]

    if includes:
        if not isinstance(includes, list):
            raise IncludeError("_include must be a list of file paths.", file_path=str(path))
        for include in includes:
            include_path = _resolve_include(path, include)
            data = _load_with_includes(include_path, child_ancestors, visited)
            merged = _deep_merge(merged, data)

    raw = _expand_dotted_keys(raw)
    merged = _deep_merge(merged, raw)
    return merged


def _resolve_include(base: Path, include: Any) -> Path:
    """
    Resolve an include entry relative to its base file.

    :param base: Path to the including file.
    :param include: Include entry value.
    :type base: pathlib.Path
    :type include: object
    :returns: Absolute path to the included file.
    :rtype: pathlib.Path
    :raises IncludeError: If the include value is invalid.
    """
    if not isinstance(include, str):
        raise IncludeError("Include paths must be strings.", file_path=str(base))
    candidate = Path(include)
    if not candidate.is_absolute():
        candidate = base.parent / candidate
    return candidate


def _expand_dotted_keys(data: dict[str, Any]) -> dict[str, Any]:
    """
    Expand top-level dotted keys into nested dicts.

    For example, ``{"a.b.c": 1}`` becomes ``{"a": {"b": {"c": 1}}}``.

    :param data: Raw config mapping.
    :type data: dict[str, Any]
    :returns: Mapping with dotted keys expanded.
    :rtype: dict[str, Any]
    """
    result: dict[str, Any] = dict()
    for key, value in data.items():
        if "." not in key:
            result[key] = value
            continue
        segments = key.split(".")
        nested: dict[str, Any] = dict()
        current = nested
        for segment in segments[:-1]:
            current[segment] = dict()
            current = current[segment]
        current[segments[-1]] = value
        result = _deep_merge(result, nested)
    return result


def _load_file(path: Path) -> dict[str, Any]:
    """
    Load a YAML or TOML file into a mapping.

    :param path: Path to the file on disk.
    :type path: pathlib.Path
    :returns: Parsed configuration mapping.
    :rtype: dict[str, Any]
    :raises ParseError: If reading or parsing fails.
    """
    suffix = path.suffix.lower()
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise ParseError(f"Failed to read config file: {path}", file_path=str(path)) from exc

    try:
        if suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except Exception as exc:  # pragma: no cover - import guard
                raise ParseError(
                    "PyYAML is required to parse YAML files.", file_path=str(path)
                ) from exc
            data = yaml.safe_load(content) or dict()
        elif suffix == ".toml":
            data = tomllib.loads(content) or dict()
        else:
            raise ParseError(f"Unsupported config format: {suffix}", file_path=str(path))
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(f"Failed to parse config file: {path}", file_path=str(path)) from exc

    if not isinstance(data, dict):
        raise ParseError("Top-level config must be a mapping.", file_path=str(path))
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep-merge two mappings (dicts merge, lists/scalars replace).

    :param base: Base mapping.
    :param override: Override mapping.
    :type base: dict[str, Any]
    :type override: dict[str, Any]
    :returns: Merged mapping.
    :rtype: dict[str, Any]
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _interpolate_config(config: dict[str, Any], *, file_path: str | None) -> dict[str, Any]:
    """
    Apply string interpolation to a config mapping.

    :param config: Raw configuration mapping.
    :param file_path: Source config path for context.
    :type config: dict[str, Any]
    :type file_path: str | None
    :returns: Interpolated mapping.
    :rtype: dict[str, Any]
    """
    resolver = _InterpolationResolver(config, file_path=file_path)
    return resolver.resolve_value(config, path=[])


class _InterpolationResolver:
    """
    Interpolation resolver for config mappings.
    """

    def __init__(self, raw: dict[str, Any], *, file_path: str | None) -> None:
        """
        Initialize the resolver.

        :param raw: Raw configuration mapping.
        :param file_path: Source config path for context.
        :type raw: dict[str, Any]
        :type file_path: str | None
        """
        self._raw = raw
        self._file_path = file_path
        self._cache: dict[str, Any] = dict()
        self._visiting: list[str] = list()

    def resolve_value(self, value: Any, *, path: list[str]) -> Any:
        """
        Resolve a value with interpolation.

        :param value: Value to resolve.
        :param path: Dotted path context.
        :type value: object
        :type path: list[str]
        :returns: Resolved value.
        :rtype: object
        """
        if isinstance(value, dict):
            return self._resolve_dict(value, path)
        if isinstance(value, list):
            return [
                self.resolve_value(item, path=path + [str(idx)])
                for idx, item in enumerate(value)
            ]
        if isinstance(value, tuple):
            return tuple(
                self.resolve_value(item, path=path + [str(idx)])
                for idx, item in enumerate(value)
            )
        if isinstance(value, str):
            return self._interpolate_string(value, path)
        return value

    def _resolve_dict(self, value: dict[str, Any], path: list[str]) -> dict[str, Any]:
        """
        Resolve a dict by interpolating keys and values.

        :param value: Mapping to resolve.
        :param path: Dotted path context.
        :type value: dict[str, Any]
        :type path: list[str]
        :returns: Resolved mapping.
        :rtype: dict[str, Any]
        """
        resolved: dict[str, Any] = dict()
        for key, val in value.items():
            new_key = (
                self.resolve_value(key, path=path + ["<key>"]) if isinstance(key, str) else key
            )
            if isinstance(new_key, str):
                key_path = path + [new_key]
            else:
                key_path = path + ["<key>"]
            new_val = self.resolve_value(val, path=key_path)
            if new_key in resolved:
                raise InterpolationError(
                    f"Interpolated key collision for '{new_key}'.",
                    file_path=self._file_path,
                    config_path=".".join(path),
                )
            resolved[new_key] = new_val
        return resolved

    def _interpolate_string(self, value: str, path: list[str]) -> Any:
        """
        Interpolate a string with placeholders.

        :param value: String value to interpolate.
        :param path: Dotted path context.
        :type value: str
        :type path: list[str]
        :returns: Interpolated string or inferred scalar.
        :rtype: object
        """
        parts, has_token, has_text = self._split_interpolation(value, path)
        if not has_token:
            if not parts:
                return value
            return "".join(payload for _, payload in parts)

        if has_token and not has_text and len(parts) == 1 and parts[0][0] == "token":
            resolved = self._resolve_placeholder(parts[0][1].strip(), path)
            if isinstance(resolved, str):
                return _infer_scalar(resolved)
            return resolved

        combined_parts: list[str] = list()
        for kind, payload in parts:
            if kind == "text":
                combined_parts.append(payload)
                continue
            resolved = self._resolve_placeholder(payload.strip(), path)
            combined_parts.append(str(resolved))
        return "".join(combined_parts)

    def _split_interpolation(
        self, value: str, path: list[str]
    ) -> tuple[list[tuple[str, str]], bool, bool]:
        """
        Split a string into interpolation and text parts.

        :param value: String value to split.
        :param path: Dotted path context.
        :type value: str
        :type path: list[str]
        :returns: tuple of parts list, has-token flag, and has-text flag.
        :rtype: tuple[list[tuple[str, str]], bool, bool]
        :raises InterpolationError: If an interpolation is unterminated.
        """
        parts: list[tuple[str, str]] = list()
        idx = 0
        has_token = False
        has_text = False
        while idx < len(value):
            if value.startswith("$${", idx):
                parts.append(("text", "${"))
                has_text = True
                idx += 3
                continue
            if value.startswith("${", idx):
                has_token = True
                idx += 2
                depth = 1
                buffer: list[str] = list()
                while idx < len(value):
                    if value.startswith("$${", idx):
                        buffer.append("${")
                        idx += 3
                        continue
                    if value.startswith("${", idx):
                        depth += 1
                        buffer.append("${")
                        idx += 2
                        continue
                    if value[idx] == "}":
                        depth -= 1
                        idx += 1
                        if depth == 0:
                            break
                        buffer.append("}")
                        continue
                    buffer.append(value[idx])
                    idx += 1
                if depth != 0:
                    raise InterpolationError(
                        "Unterminated interpolation.",
                        file_path=self._file_path,
                        config_path=".".join(path),
                    )
                parts.append(("token", "".join(buffer)))
                continue
            parts.append(("text", value[idx]))
            has_text = True
            idx += 1
        return parts, has_token, has_text

    def _resolve_placeholder(self, token: str, path: list[str]) -> Any:
        """
        Resolve a single interpolation token.

        Resolution order:
        1. Config path lookup (if the key exists in the config tree).
        2. Environment variable lookup.
        3. Default value (if provided via ``:-``).

        :param token: Token inside ``${...}``.
        :param path: Dotted path context.
        :type token: str
        :type path: list[str]
        :returns: Resolved value for the token.
        :rtype: object
        :raises InterpolationError: If the token cannot be resolved.
        """
        if ":-" in token:
            key, default = token.split(":-", 1)
            key = key.strip()
            default = default.strip()
        else:
            key = token.strip()
            default = None

        config_value = _get_by_path(self._raw, key)
        if config_value is not _MISSING:
            return self._resolve_config_path(key, path)

        env_value = os.environ.get(key)
        if env_value is not None:
            return env_value

        if default is not None:
            return self._interpolate_string(default, path)

        raise InterpolationError(
            f"Interpolation target '{key}' not found in config or environment.",
            file_path=self._file_path,
            config_path=".".join(path),
        )

    def _resolve_config_path(self, key: str, path: list[str]) -> Any:
        """
        Resolve a config path interpolation.

        :param key: Dotted config path.
        :param path: Dotted path context.
        :type key: str
        :type path: list[str]
        :returns: Resolved config value.
        :rtype: object
        :raises InterpolationError: If the path is missing.
        """
        dotted = key
        if dotted in self._cache:
            return self._cache[dotted]
        if dotted in self._visiting:
            raise CircularInterpolationError(
                f"Circular interpolation detected for '{dotted}'.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        raw_value = _get_by_path(self._raw, dotted)
        if raw_value is _MISSING:
            raise InterpolationError(
                f"Interpolation target '{dotted}' not found.",
                file_path=self._file_path,
                config_path=".".join(path),
            )
        self._visiting.append(dotted)
        resolved = self.resolve_value(raw_value, path=dotted.split("."))
        self._visiting.pop()
        self._cache[dotted] = resolved
        return resolved


_MISSING = object()


def _get_by_path(data: Any, dotted: str) -> Any:
    """
    Resolve a dotted path into a nested structure.

    :param data: Root data structure.
    :param dotted: Dotted path to resolve.
    :type data: object
    :type dotted: str
    :returns: Resolved value or ``_MISSING`` sentinel.
    :rtype: object
    """
    current = data
    if dotted == "":
        return _MISSING
    for segment in dotted.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list):
            if not segment.isdigit():
                return _MISSING
            idx = int(segment)
            if idx < 0 or idx >= len(current):
                return _MISSING
            current = current[idx]
        else:
            return _MISSING
    return current


def _infer_scalar(value: str) -> Any:
    """
    Infer a scalar type from a string.

    :param value: String value to coerce.
    :type value: str
    :returns: Inferred scalar type or original string.
    :rtype: object
    """
    lowered = value.strip().lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    if lowered in {"null", "none"}:
        return None
    try:
        stripped = value.strip()
        if _INTEGER_RE.match(stripped):
            return int(stripped)
        if _FLOAT_RE.match(stripped) or _SCI_INT_RE.match(stripped):
            return float(stripped)
    except Exception:
        return value
    return value


if __name__ == "__main__":
    pass
