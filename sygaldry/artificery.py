from __future__ import annotations

__author__ = "Rohan B. Dalton"

import asyncio
import inspect
import warnings
from contextlib import AsyncExitStack, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cache import _NOT_FOUND, Instances, _canonical_hash
from .configuration import (
    _MISSING,
    _deep_merge,
    _expand_dotted_keys,
    _get_by_path,
    _interpolate_config,
    _is_url,
    _load_with_includes,
    _maybe_download,
    _record_sources,
)
from .errors import (
    CircularReferenceError,
    ConfigReferenceError,
    ConstructorError,
    ImportResolutionError,
    LifecycleError,
    ResolutionError,
    SygaldryError,
    ValidationError,
)
from .secrets import protect_secrets, reveal
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


def _copy_config(value: Any) -> Any:
    """Copy config containers while preserving supplied application object identity."""
    if isinstance(value, dict):
        result = {key: _copy_config(child) for key, child in value.items()}
    elif isinstance(value, list):
        result = [_copy_config(child) for child in value]
    elif isinstance(value, tuple):
        result = tuple(_copy_config(child) for child in value)
    else:
        result = value
    return result


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


def resolve_config(  # noqa: PLR0913
    config: dict[str, Any],
    *,
    file_path: str | None = None,
    cache: Instances | None = None,
    transient: bool = False,
    strict: bool = True,
    key: str | None = None,
) -> Any:
    """
    Resolve a config mapping into an instantiated object graph.

    :param config: Configuration mapping.
    :param file_path: Source config path for context.
    :param cache: Optional instance cache.
    :param transient: Isolate named sharing from any supplied cache; refs keep identity.
    :param strict: Reject unknown constructor kwargs by default.
    :param key: Optional dotted key to resolve instead of the whole graph.
    :type config: dict[str, Any]
    :type file_path: str | None
    :type cache: Instances | None
    :type transient: bool
    :returns: Resolved configuration mapping.
    :rtype: dict[str, Any]
    """

    artificery = Artificery(
        config=config, source=file_path, cache=cache, transient=transient, strict=strict
    )
    resolved = artificery.resolve(key)
    return resolved


class Artificery:
    """Prepare configuration and own the identity and lifetime of its object graph.

    Use ``with`` or ``async with`` when constructing managed resources. Resolve
    one dotted key with ``resolve(key)`` or ``await aresolve(key)``. Validation
    imports targets and checks their signatures without invoking constructors.
    """

    def __init__(  # noqa: PLR0913
        self,
        *paths: str | Path,
        config: dict[str, Any] | None = None,
        source: str | None = None,
        overrides: dict[str, Any] | None = None,
        uses: dict[str, str] | None = None,
        cache: Instances | None = None,
        transient: bool = False,
        strict: bool = True,
    ) -> None:
        if not paths and config is None:
            raise ValueError("Artificery requires at least one path or a config dict.")
        else:
            pass
        self._paths = tuple(paths)
        self._raw_config = config
        self._source = source
        self._overrides = overrides or dict()
        self._uses = uses or dict()
        self._owns_cache = transient or cache is None
        self._cache = Instances() if self._owns_cache else cache
        self._strict = strict
        self._prepared: dict[str, Any] | None = None
        self._sources: dict[tuple[str, ...], str] = dict()
        self._nodes: dict[tuple[str, ...], Any] = dict()
        self._visiting: list[tuple[str, ...]] = list()
        self._construction_owners: list[Any] = [self]
        self._managed_owners: dict[tuple[str, ...], Any] = dict()
        self._references: dict[tuple[str, ...], tuple[str, ...]] = dict()
        self._targets: dict[str, Any] = dict()
        self._validated_kwargs: dict[tuple[str, ...], tuple[str, ...]] = dict()
        self._stack = AsyncExitStack()
        self._scope_active = False
        self._closed = False
        self._sync_loop: asyncio.AbstractEventLoop | None = None
        self._resolution_lock = asyncio.Lock()
        self._borrowed_owners: set[Instances] = set()

    @property
    def closed(self) -> bool:
        """Whether this runtime has released its owned resources."""
        result = self._closed
        return result

    @property
    def config(self) -> dict[str, Any]:
        """Loaded, merged, overridden and interpolated config, without construction."""
        if self._prepared is None:
            self._prepared = self._prepare()
        else:
            pass
        result = self._prepared
        return result

    def _source_for(self, path: tuple[str, ...]) -> str | None:
        for length in range(len(path), -1, -1):
            if source := self._sources.get(path[:length]):
                return source
            else:
                pass
        else:  # noqa: PLW0120
            source = self._source
            return source

    def _error(self, error_type: type[SygaldryError], message: str, path: tuple[str, ...]):
        error = error_type(
            message, file_path=self._source_for(path), config_path=".".join(path)
        )
        return error

    def _prepare(self) -> dict[str, Any]:
        merged: dict[str, Any] = dict()
        for path in self._paths:
            local = _maybe_download(path)
            try:
                incoming = _load_with_includes(
                    local,
                    ancestors=[],
                    visited=set(),
                    sources=self._sources,
                    source_label=str(path) if _is_url(path) else None,
                )
                merged = _deep_merge(merged, incoming)
            finally:
                if _is_url(path):
                    local.unlink(missing_ok=True)
                else:
                    pass
        if self._raw_config is not None:
            incoming = _expand_dotted_keys(_copy_config(self._raw_config))
            _record_sources(incoming, self._sources, self._source or "<config>")
            merged = _deep_merge(merged, incoming)
        else:
            pass
        for target_path, source_path in self._uses.items():
            value = _get_by_path(merged, source_path)
            if value is _MISSING:
                raise self._error(
                    ConfigReferenceError,
                    f"Use source '{source_path}' not found.",
                    tuple(target_path.split(".")),
                )
            else:
                _set_by_path(merged, target_path, _copy_config(value))
                _record_sources(
                    value,
                    self._sources,
                    self._source_for(tuple(source_path.split("."))) or "<use>",
                    tuple(target_path.split(".")),
                )
        for key, value in self._overrides.items():
            _set_by_path(merged, key, _copy_config(value))
            _record_sources(value, self._sources, "<override>", tuple(key.split(".")))
        merged = protect_secrets(merged)
        prepared = _interpolate_config(merged, file_path=self._source, sources=self._sources)
        return prepared

    def _raw_target(self, key: str, requester: tuple[str, ...]):
        if not isinstance(key, str) or not key:
            raise self._error(
                ConfigReferenceError, "Reference must be a non-empty dotted path.", requester
            )
        else:
            pass
        current: Any = self.config
        path: tuple[str, ...] = tuple()
        segments = key.split(".")
        for index, segment in enumerate(segments):
            if isinstance(current, dict) and any(
                marker in current for marker in ("_type", "_func", "_ref", "_entries")
            ):
                result = (current, path, segments[index:])
                return result
            elif isinstance(current, dict) and segment in current:
                current = current[segment]
            elif (
                isinstance(current, (list, tuple))
                and segment.isdigit()
                and int(segment) < len(current)
            ):
                current = current[int(segment)]
            elif not isinstance(current, (dict, list, tuple)):
                result = (current, path, segments[index:])
                return result
            else:
                raise self._error(
                    ConfigReferenceError,
                    f"Reference target '{key}' not found. Available top-level keys: {sorted(self.config)}.",
                    requester,
                )
            path += (segment,)
        else:  # noqa: PLW0120
            result = (current, path, list())
            return result

    def _target(self, dotted: str, path: tuple[str, ...]):
        if not isinstance(dotted, str) or not dotted:
            raise self._error(
                ImportResolutionError, "Dotted path must be a non-empty string.", path
            )
        else:
            pass
        if dotted not in self._targets:
            self._targets[dotted] = import_dotted_path(
                dotted, file_path=self._source_for(path), config_path=".".join(path)
            )
        else:
            pass
        target = self._targets[dotted]
        return target

    def _constructor_spec(self, value: dict[str, Any], path: tuple[str, ...]):
        args = value.get("_args", [])
        extra_kwargs = value.get("_kwargs", {})
        if not isinstance(args, list):
            raise self._error(ResolutionError, "_args must be a list.", path + ("_args",))
        elif not isinstance(extra_kwargs, dict):
            raise self._error(
                ResolutionError, "_kwargs must be a mapping.", path + ("_kwargs",)
            )
        else:
            kwargs = {key: child for key, child in value.items() if key not in RESERVED_KEYS}
            kwargs.update(extra_kwargs)
        result = (args, kwargs)
        return result

    def validate(self, key: str | None = None) -> None:
        """Check selected nodes and their dependencies without constructing anything."""
        done: set[tuple[str, ...]] = set()
        visiting: set[tuple[str, ...]] = set()

        def visit(value: Any, path: tuple[str, ...]) -> None:
            if path in done:
                return
            elif path in visiting:
                raise self._error(CircularReferenceError, "Circular reference detected.", path)
            else:
                visiting.add(path)
            if isinstance(value, dict):
                for child, child_path in self._validation_children(value, path):
                    visit(child, child_path)
            elif isinstance(value, (list, tuple)):
                for index, child in enumerate(value):
                    visit(child, path + (str(index),))
            else:
                pass
            visiting.remove(path)
            done.add(path)

        if key is None:
            visit(self.config, tuple())
        else:
            value, path, _ = self._raw_target(key, tuple(key.split(".")))
            visit(value, path)

    def _validate_type(self, value: dict[str, Any], path: tuple[str, ...]):
        if "_func" in value:
            raise self._error(ValidationError, "_type and _func are mutually exclusive.", path)
        elif "_instance" in value and (
            not isinstance(value["_instance"], str) or not value["_instance"]
        ):
            raise self._error(
                ValidationError, "_instance must be a non-empty string.", path + ("_instance",)
            )
        elif value.get("_lifecycle", "auto") not in ("auto", "context", "close", "external"):
            raise self._error(
                ValidationError,
                "_lifecycle must be auto, context, close, or external.",
                path + ("_lifecycle",),
            )
        else:
            args, kwargs = self._constructor_spec(value, path)
            target = self._target(value["_type"], path + ("_type",))
            if not callable(target):
                raise self._error(
                    ValidationError,
                    "_type must resolve to a callable constructor.",
                    path + ("_type",),
                )
            else:
                pass
            keyword_paths = {
                name: path
                + (("_kwargs", name) if name in value.get("_kwargs", {}) else (name,))
                for name in kwargs
            }
            filtered = _validate_signature(
                target,
                tuple(args),
                kwargs,
                strict=self._strict,
                file_path=self._source_for(path + ("_type",)),
                config_path=".".join(path),
                source_for=self._source_for,
                keyword_paths=keyword_paths,
            )
            self._validated_kwargs[path] = tuple(filtered)
        children = [(child, path + ("_args", str(index))) for index, child in enumerate(args)]
        children.extend((child, keyword_paths[name]) for name, child in filtered.items())
        return children

    def _validate_entries(self, value: dict[str, Any], path: tuple[str, ...]):
        entries = value["_entries"]
        if set(value) != {"_entries"} or not isinstance(entries, list):
            raise self._error(
                ResolutionError, "_entries must be a list and the only key.", path
            )
        else:
            children = list()
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict) or set(entry) != {"_key", "_value"}:
                    raise self._error(
                        ResolutionError,
                        "Each _entries item must contain _key and _value.",
                        path + ("_entries", str(index)),
                    )
                else:
                    children.append((entry, path + ("_entries", str(index))))
        return children

    def _validate_func(self, value: dict[str, Any], path: tuple[str, ...]):
        if set(value) != {"_func"}:
            raise self._error(
                ValidationError,
                f"_func does not accept other keys: {sorted(set(value) - {'_func'})}.",
                path,
            )
        elif not callable(self._target(value["_func"], path + ("_func",))):
            raise self._error(ValidationError, "_func must resolve to a callable.", path)
        else:
            pass

    def _validation_children(self, value: dict[str, Any], path: tuple[str, ...]):
        if "_secret" in value:
            raise self._error(
                ValidationError, "_secret must be the only key in its mapping.", path
            )
        elif "_ref" in value:
            if len(value) != 1:
                raise self._error(
                    ValidationError, "_ref must be the only key in its mapping.", path
                )
            else:
                target_value, target_path, _ = self._raw_target(value["_ref"], path)
                children = [(target_value, target_path)]
        elif "_type" in value:
            children = self._validate_type(value, path)
        elif "_func" in value:
            self._validate_func(value, path)
            children = list()
        elif "_instance" in value or "_lifecycle" in value:
            raise self._error(
                ValidationError, "_instance and _lifecycle are only valid with _type.", path
            )
        elif value.get("_deep") is False:
            children = list()
        elif "_entries" in value:
            children = self._validate_entries(value, path)
        else:
            children = [(child, path + (str(key),)) for key, child in value.items()]
        return children

    def _check_lifetime(self) -> None:
        if self._closed:
            raise LifecycleError("This runtime has closed.")
        elif self._cache.closed:
            raise LifecycleError("The shared cache has closed.")
        elif any(owner.closed for owner in self._borrowed_owners):
            raise LifecycleError("The cache owning a borrowed shared resource has closed.")
        else:
            pass

    def _run_sync(self, awaitable):
        if self._cache._scope_active:
            result = self._cache._run_sync(awaitable)
            return result
        else:
            pass
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            awaitable.close()
            raise LifecycleError("Use aresolve/aclose inside an active event loop.")
        if self._sync_loop is None:
            self._sync_loop = asyncio.new_event_loop()
        else:
            pass
        result = self._sync_loop.run_until_complete(awaitable)
        return result

    def resolve(self, key: str | None = None) -> Any:
        """Resolve a full graph or one key, preserving identity for this runtime."""
        try:
            result = self._run_sync(self.aresolve(key))
        finally:
            if not self._scope_active:
                self._close_loop()
            else:
                pass
        return result

    async def aresolve(self, key: str | None = None) -> Any:
        """Await constructors and resolve a full graph or a selected dependency graph."""
        self._check_lifetime()
        async with self._resolution_lock:
            self._check_lifetime()
            self.validate(key)
            if key is None:
                result = await self._resolve_value(self.config, tuple())
            else:
                result = await self._resolve_ref(key, tuple(key.split(".")))
        return result

    def __enter__(self):
        self._check_lifetime()
        if self._scope_active:
            raise LifecycleError("Runtime scopes cannot be nested or entered twice.")
        else:
            self._scope_active = True
            if self._owns_cache:
                self._cache.__enter__()
                self._stack.push_async_exit(self._cache.__aexit__)
            else:
                pass
        result = self
        return result

    def __exit__(self, exception_type, exception, traceback):
        try:
            result = self._run_sync(self.__aexit__(exception_type, exception, traceback))
        finally:
            self._close_loop()
        return result

    async def __aenter__(self):
        result = self.__enter__()
        return result

    async def __aexit__(self, exception_type, exception, traceback):
        try:
            result = await self._stack.__aexit__(exception_type, exception, traceback)
        finally:
            self._closed = True
            self._scope_active = False
        return result

    def _close_loop(self):
        if self._owns_cache and self._cache.closed:
            self._cache._close_loop()
        else:
            pass
        if self._sync_loop is not None:
            try:
                self._sync_loop.run_until_complete(self._sync_loop.shutdown_asyncgens())
            finally:
                self._sync_loop.close()
                self._sync_loop = None
        else:
            pass

    def close(self) -> None:
        try:
            self._run_sync(self.aclose())
        finally:
            self._close_loop()

    async def aclose(self) -> None:
        if self._closed:
            pass
        else:
            await self.__aexit__(None, None, None)

    def _check_dependency_ownership(self, path: tuple[str, ...]):
        if self._construction_owners[-1] is self:
            return
        else:
            pass
        checked: set[tuple[str, ...]] = set()

        def check(current_path):
            if current_path in checked:
                return
            else:
                checked.add(current_path)
            for managed_path, owner in self._managed_owners.items():
                if managed_path[: len(current_path)] == current_path and owner is self:
                    raise self._error(
                        LifecycleError,
                        "A shared component cannot borrow a runtime-owned resource. Give the dependency an _instance tag or mark it external.",
                        path,
                    )
                else:
                    pass
            for reference_path, target_path in self._references.items():
                if reference_path[: len(current_path)] == current_path:
                    check(target_path)
                else:
                    pass

        check(path)

    def _fingerprint(self, value: Any):
        if isinstance(value, dict) and "_ref" in value:
            target, _, remainder = self._raw_target(value["_ref"], tuple())
            result = {
                "ref": value["_ref"],
                "target": self._fingerprint(target),
                "attributes": remainder,
            }
        elif isinstance(value, dict):
            result = {key: self._fingerprint(child) for key, child in value.items()}
        elif isinstance(value, (list, tuple)):
            result = [self._fingerprint(child) for child in value]
        else:
            result = reveal(value)
        return result

    async def _resolve_value(self, value: Any, path: tuple[str, ...]) -> Any:
        if path in self._nodes:
            self._check_dependency_ownership(path)
            result = self._nodes[path]
            return result
        elif path in self._visiting:
            raise self._error(CircularReferenceError, "Circular reference detected.", path)
        else:
            self._visiting.append(path)
        try:
            if isinstance(value, dict):
                result = await self._resolve_mapping(value, path)
            elif isinstance(value, (list, tuple)):
                children = list()
                for index, child in enumerate(value):
                    children.append(await self._resolve_value(child, path + (str(index),)))
                result = tuple(children) if isinstance(value, tuple) else children
            else:
                result = reveal(value)
            self._nodes[path] = result
        finally:
            self._visiting.pop()
        return result

    async def _resolve_mapping(self, value: dict[str, Any], path: tuple[str, ...]):
        if "_ref" in value:
            result = await self._resolve_ref(value["_ref"], path)
        elif "_type" in value:
            result = await self._resolve_type(value, path)
        elif "_func" in value:
            result = self._target(value["_func"], path + ("_func",))
        elif value.get("_deep") is False:
            result = reveal({key: child for key, child in value.items() if key != "_deep"})
        elif "_entries" in value:
            result = await self._resolve_entries(value["_entries"], path)
        else:
            result = dict()
            for child_key, child in value.items():
                result[child_key] = await self._resolve_value(child, path + (str(child_key),))
        return result

    async def _resolve_ref(self, key: str, path: tuple[str, ...]):
        value, target_path, remainder = self._raw_target(key, path)
        self._references[path] = target_path
        self._check_dependency_ownership(target_path)
        # References borrow their target's lifetime; inline children inherit the parent's.
        self._construction_owners.append(self)
        try:
            target = await self._resolve_value(value, target_path)
        finally:
            self._construction_owners.pop()
        self._check_dependency_ownership(target_path)
        for segment in remainder:
            if isinstance(target, dict) and segment in target:
                target = target[segment]
            elif (
                isinstance(target, (list, tuple))
                and segment.isdigit()
                and int(segment) < len(target)
            ):
                target = target[int(segment)]
            else:
                try:
                    target = getattr(target, segment)
                except AttributeError as exc:
                    raise self._error(
                        ConfigReferenceError,
                        f"Attribute '{segment}' not found on reference '{key}'.",
                        path,
                    ) from exc
        return target

    async def _resolve_entries(self, entries: list[Any], path: tuple[str, ...]):
        result = dict()
        for index, entry in enumerate(entries):
            entry_path = path + ("_entries", str(index))
            key = await self._resolve_value(entry["_key"], entry_path + ("_key",))
            value = await self._resolve_value(entry["_value"], entry_path + ("_value",))
            try:
                hash(key)
            except TypeError as exc:
                raise self._error(
                    ResolutionError,
                    "Resolved _entries keys must be hashable.",
                    entry_path + ("_key",),
                ) from exc
            if key in result:
                raise self._error(
                    ResolutionError, "Duplicate _entries key.", entry_path + ("_key",)
                )
            else:
                result[key] = value
        return result

    async def _finish(self, callback):
        result = callback()
        if inspect.isawaitable(result):
            await result
        else:
            pass

    async def _register_close(self, value: Any, close, lifecycle: str, stack: AsyncExitStack):
        stack.push_async_callback(self._finish, close)
        opening = getattr(value, "aopen", None) or getattr(value, "open", None)
        if lifecycle == "auto" and callable(opening):
            await self._finish(opening)
        else:
            pass

    async def _enter_resource(self, value: Any, lifecycle: str, stack: AsyncExitStack):
        if (
            lifecycle != "close"
            and hasattr(value, "__aenter__")
            and hasattr(value, "__aexit__")
        ):
            result = await stack.enter_async_context(value)
        elif (
            lifecycle != "close" and hasattr(value, "__enter__") and hasattr(value, "__exit__")
        ):
            result = stack.enter_context(value)
        elif callable(
            close := getattr(value, "aclose", None) or getattr(value, "close", None)
        ):
            await self._register_close(value, close, lifecycle, stack)
            result = value
        else:
            result = value
        return result

    async def _adopt(self, value: Any, lifecycle: str, path: tuple[str, ...], *, owner: Any):
        if lifecycle == "external":
            result = (value, False)
            return result
        else:
            pass
        has_async_context = hasattr(value, "__aenter__") and hasattr(value, "__aexit__")
        has_context = hasattr(value, "__enter__") and hasattr(value, "__exit__")
        close = getattr(value, "aclose", None) or getattr(value, "close", None)
        managed = has_async_context or has_context or callable(close)
        if lifecycle == "context" and not (has_async_context or has_context):
            raise self._error(
                LifecycleError, "The component does not implement a context manager.", path
            )
        elif lifecycle == "close" and not callable(close):
            raise self._error(
                LifecycleError, "The component does not provide close/aclose.", path
            )
        elif managed and (not self._scope_active or not owner._scope_active):
            if callable(close):
                await self._finish(close)
            else:
                pass
            raise self._error(
                LifecycleError,
                "Managed resources require a runtime scope and, for shared resources, a cache scope.",
                path,
            )
        else:
            if managed and owner is self._cache:
                self._cache._bind_resource_loop()
            else:
                pass
            value = await self._enter_resource(value, lifecycle, owner._stack)
        result = (value, managed)
        return result

    async def _resolve_type(self, value: dict[str, Any], path: tuple[str, ...]):
        instance = value.get("_instance")
        owner = (
            self._cache
            if instance is not None and not self._owns_cache
            else self._construction_owners[-1]
        )
        self._construction_owners.append(owner)
        try:
            type_path = value["_type"]
            lifecycle = value.get("_lifecycle", "auto")
            if instance is not None:
                raw_args, raw_kwargs = self._constructor_spec(value, path)
                filtered = {
                    key: child
                    for key, child in raw_kwargs.items()
                    if key in self._validated_kwargs[path]
                }
                spec = {
                    "args": self._fingerprint(raw_args),
                    "kwargs": self._fingerprint(filtered),
                    "lifecycle": lifecycle,
                }
                spec_hash = _canonical_hash(tuple(), spec)
            else:
                spec_hash = ""
            lock = (
                self._cache.claim(
                    type_path,
                    instance,
                    spec_hash,
                    file_path=self._source_for(path),
                    config_path=".".join(path),
                )
                if instance is not None
                else nullcontext()
            )
            async with lock:
                existing = (
                    self._cache.get(
                        type_path,
                        instance,
                        expected_hash=spec_hash,
                        file_path=self._source_for(path),
                        config_path=".".join(path),
                    )
                    if instance is not None
                    else _NOT_FOUND
                )
                if existing is not _NOT_FOUND:
                    cached_owner = self._cache.owner(type_path, instance)
                    if cached_owner is not None:
                        cached_owner._bind_resource_loop()
                        self._borrowed_owners.add(cached_owner)
                    else:
                        pass
                    result = existing
                else:
                    result = await self._construct_type(value, path, owner)
                    if instance is not None:
                        managed = (
                            self._managed_owners.get(path) is self._cache
                            or owner is self._cache
                            and self._cache in self._borrowed_owners
                        )
                        self._cache.set(
                            type_path,
                            instance,
                            result,
                            spec_hash=spec_hash,
                            owner=self._cache if managed else None,
                            file_path=self._source_for(path),
                            config_path=".".join(path),
                        )
                    else:
                        pass
        finally:
            self._construction_owners.pop()
        return result

    def _check_resource_scope(self, target, lifecycle, path, owner):
        known_resource = any(
            hasattr(target, name) for name in ("__enter__", "__aenter__", "close", "aclose")
        )
        if lifecycle != "external" and known_resource:
            if not self._scope_active or not owner._scope_active:
                raise self._error(
                    LifecycleError,
                    "Managed resources require a runtime scope and shared resources require a cache scope.",
                    path,
                )
            elif owner is self._cache:
                self._cache._bind_resource_loop()
            else:
                pass
        else:
            pass

    async def _construct_type(self, value: dict[str, Any], path: tuple[str, ...], owner: Any):
        type_path = value["_type"]
        target = self._target(type_path, path + ("_type",))
        lifecycle = value.get("_lifecycle", "auto")
        self._check_resource_scope(target, lifecycle, path, owner)
        raw_args, raw_kwargs = self._constructor_spec(value, path)
        raw_kwargs = {
            key: child
            for key, child in raw_kwargs.items()
            if key in self._validated_kwargs[path]
        }
        args = list()
        for index, child in enumerate(raw_args):
            args.append(await self._resolve_value(child, path + ("_args", str(index))))
        kwargs = dict()
        for key, child in raw_kwargs.items():
            child_path = path + (
                ("_kwargs", key) if key in value.get("_kwargs", {}) else (key,)
            )
            kwargs[key] = await self._resolve_value(child, child_path)
        try:
            result = target(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
            else:
                pass
        except Exception as exc:
            raise self._error(
                ConstructorError,
                f"Failed to construct '{type_path}'.",
                path + ("_type",),
            ) from exc
        result, managed = await self._adopt(result, lifecycle, path, owner=owner)
        if managed:
            self._managed_owners[path] = owner
            if owner is self._cache:
                self._borrowed_owners.add(self._cache)
            else:
                pass
        else:
            pass
        return result


def _validate_signature(  # noqa: PLR0913
    target: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    file_path: str | None,
    config_path: str,
    strict: bool = True,
    source_for: Any = None,
    keyword_paths: dict[str, tuple[str, ...]] | None = None,
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
        if extras and strict:
            name = sorted(extras)[0]
            field_path = (keyword_paths or {}).get(
                name, tuple(config_path.split(".")) + (name,)
            )
            raise ConstructorError(
                f"Unknown constructor kwargs: {sorted(extras)}.",
                file_path=source_for(field_path) if source_for else file_path,
                config_path=".".join(field_path),
            )
        elif extras:
            warnings.warn(
                f"Extra kwargs for '{getattr(target, '__name__', target)}': {sorted(extras)}",
                RuntimeWarning,
                stacklevel=2,
            )
            kwargs = {key: value for key, value in kwargs.items() if key not in extras}
        else:
            pass
    else:
        pass

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
