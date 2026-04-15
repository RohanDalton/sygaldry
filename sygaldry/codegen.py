from __future__ import annotations

__author__ = "Rohan B. Dalton"

import importlib
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .types import RESERVED_KEYS

_NON_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9_]")


@dataclass(frozen=True)
class SourceMapping:
    """
    Map a generated line number to a config path.
    """

    line: int
    config_path: str


@dataclass
class ComponentEntry:
    """
    A typed component extracted from the config.
    """

    config_path: str
    var_name: str
    import_path: str
    args: list[Any] = field(default_factory=list)
    kwargs: dict[str, Any] = field(default_factory=dict)
    is_func: bool = False


@dataclass
class PlainEntry:
    """
    A plain (non-typed) config value.
    """

    config_path: str
    var_name: str
    value: Any


@dataclass
class RefExpression:
    """
    A reference expression to be emitted as a variable or attribute access.
    """

    target: str


@dataclass
class EntriesExpression:
    """
    A dict built from _entries.
    """

    items: list[tuple[Any, Any]]


@dataclass
class AnalysisResult:
    """
    Result of analyzing a config dict.
    """

    components: list[ComponentEntry] = field(default_factory=list)
    plains: list[PlainEntry] = field(default_factory=list)
    topological_order: list[str] = field(default_factory=list)
    imports: dict[str, tuple[str, str]] = field(default_factory=dict)


def _to_identifier(key: str) -> str:
    """
    Convert a config key to a valid Python identifier.
    """
    if result := _NON_IDENTIFIER_RE.sub("_", key):
        if result[0].isdigit():
            result = f"_{result}"
        return result
    else:
        return "_unnamed"


def _split_import_path(dotted: str) -> tuple[str, str]:
    """
    Split 'a.b.ClassName' into ('a.b', 'ClassName').
    """
    parts = dotted.rsplit(".", 1)
    if len(parts) == 1:
        return parts[0], parts[0]
    else:
        return parts[0], parts[1]


class ConfigAnalyzer:
    """
    Walk a loaded config dict and extract typed component specs.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._components: list[ComponentEntry] = list()
        self._plains: list[PlainEntry] = list()
        self._imports: dict[str, tuple[str, str]] = dict()
        self._deps: dict[str, list[str]] = dict()
        self._variable_names: dict[str, str] = dict()
        self._anon_counter = 0
        self._used_names: set[str] = set()

    def analyze(self) -> AnalysisResult:
        """
        Analyze the config and return structured results.
        """
        for key, value in self._config.items():
            self._analyze_top_level(key, value)
        order = self._topological_sort()
        result = AnalysisResult(
            components=self._components,
            plains=self._plains,
            topological_order=order,
            imports=self._imports,
        )
        return result

    def _alloc_name(self, preferred: str) -> str:
        """
        Allocate a unique variable name.
        """
        name = _to_identifier(preferred)
        if name not in self._used_names:
            self._used_names.add(name)
            return name
        else:
            counter = 0
            while f"{name}_{counter}" in self._used_names:
                counter += 1
            unique = f"{name}_{counter}"
            self._used_names.add(unique)
            return unique

    def _alloc_anon(self, hint: str) -> str:
        """
        Allocate an anonymous variable name.
        """
        name = f"__sygaldry_{_to_identifier(hint)}_{self._anon_counter}"
        self._anon_counter += 1
        self._used_names.add(name)
        return name

    def _analyze_top_level(self, key: str, value: Any) -> None:
        """
        Analyze a single top-level config entry.
        """
        variable_name = self._alloc_name(key)
        self._variable_names[key] = variable_name
        self._deps[key] = list()

        if isinstance(value, dict):
            if "_ref" in value:
                ref_target = value["_ref"]
                top = ref_target.split(".")[0]
                self._deps[key].append(top)
                self._plains.append(
                    PlainEntry(
                        config_path=key,
                        var_name=variable_name,
                        value=RefExpression(target=ref_target),
                    )
                )
            elif "_type" in value:
                self._analyze_type_entry(key, variable_name, value)
            elif "_func" in value:
                self._analyze_func_entry(key, variable_name, value)
            elif value.get("_deep") is False:
                self._plains.append(
                    PlainEntry(config_path=key, var_name=variable_name, value=...)
                )
            elif "_entries" in value:
                entries_expr = self._analyze_entries(value["_entries"], key, self._deps[key])
                self._plains.append(
                    PlainEntry(config_path=key, var_name=variable_name, value=entries_expr)
                )
            else:
                self._plains.append(
                    PlainEntry(config_path=key, var_name=variable_name, value=value)
                )
        else:
            self._plains.append(
                PlainEntry(config_path=key, var_name=variable_name, value=value)
            )

    def _analyze_type_entry(
        self, config_path: str, var_name: str, entry: dict[str, Any]
    ) -> None:
        """
        Analyze a _type entry.
        """
        import_path = entry["_type"]
        mod, name = _split_import_path(import_path)
        self._imports[import_path] = (mod, name)

        raw_args = entry.get("_args", [])
        args = list()
        for idx, arg in enumerate(raw_args):
            processed = self._process_arg_value(
                arg, f"{config_path}._args.{idx}", self._deps.setdefault(config_path, [])
            )
            args.append(processed)

        kwargs: dict[str, Any] = dict()
        for key, value in entry.items():
            if key in RESERVED_KEYS:
                continue
            processed = self._process_arg_value(
                value, f"{config_path}.{key}", self._deps.setdefault(config_path, [])
            )
            kwargs[key] = processed

        raw_kwargs = entry.get("_kwargs", {})
        for key, value in raw_kwargs.items():
            processed = self._process_arg_value(
                value, f"{config_path}._kwargs.{key}", self._deps.setdefault(config_path, [])
            )
            kwargs[key] = processed

        self._components.append(
            ComponentEntry(
                config_path=config_path,
                var_name=var_name,
                import_path=import_path,
                args=args,
                kwargs=kwargs,
            )
        )

    def _analyze_func_entry(
        self, config_path: str, var_name: str, value: dict[str, Any]
    ) -> None:
        """
        Analyze a _func entry.
        """
        import_path = value["_func"]
        module, name = _split_import_path(import_path)
        self._imports[import_path] = (module, name)
        component = ComponentEntry(
            config_path=config_path,
            var_name=var_name,
            import_path=import_path,
            is_func=True,
        )
        self._components.append(component)

    def _process_arg_value(self, value: Any, config_path: str, deps: list[str]) -> Any:
        """
        Process a value that appears as an argument to a _type constructor.

        Returns the value as-is for scalars, as a RefExpression for _ref,
        or hoists nested _type entries to intermediate variables.
        """
        if not isinstance(value, dict):
            if isinstance(value, list):
                return [
                    self._process_arg_value(item, f"{config_path}.{idx}", deps)
                    for idx, item in enumerate(value)
                ]
            return value

        if "_ref" in value:
            ref_target = value["_ref"]
            top = ref_target.split(".")[0]
            deps.append(top)
            return RefExpression(target=ref_target)

        elif "_type" in value:
            anon_name = self._alloc_anon(config_path.replace(".", "_"))
            self._analyze_type_entry(config_path, anon_name, value)
            return RefExpression(target=anon_name)

        elif "_func" in value:
            anon_name = self._alloc_anon(config_path.replace(".", "_"))
            self._analyze_func_entry(config_path, anon_name, value)
            return RefExpression(target=anon_name)

        elif value.get("_deep") is False:
            return ...

        elif "_entries" in value:
            return self._analyze_entries(value["_entries"], config_path, deps)

        else:
            return value

    def _analyze_entries(
        self, entries: Any, config_path: str, deps: list[str]
    ) -> EntriesExpression:
        """
        Analyze an _entries list.
        """
        items: list[tuple[Any, Any]] = list()
        if not isinstance(entries, list):
            return EntriesExpression(items=[])
        for idx, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            key = self._process_arg_value(entry.get("_key"), f"{config_path}.{idx}._key", deps)
            value = self._process_arg_value(
                entry.get("_value"), f"{config_path}.{idx}._value", deps
            )
            item = (key, value)
            items.append(item)
        return EntriesExpression(items=items)

    def _topological_sort(self) -> list[str]:
        """
        Sort entries so that dependencies come before dependents.
        """
        visited: set[str] = set()
        order: list[str] = list()
        visiting: set[str] = set()

        keys = {component.config_path for component in self._components}
        keys.update({plain.config_path for plain in self._plains})

        def visit(key_: str) -> None:
            # What the absolute fuck?:w
            if key_ in visited or key_ in visiting:
                return

            visiting.add(key_)
            for dep in self._deps.get(key_, []):
                if dep in keys:
                    visit(dep)
            visiting.discard(key_)
            visited.add(key_)
            order.append(key_)

        for key in keys:
            visit(key)

        return order


class CodeGenerator:
    """
    Generate Python source code from analysis results.
    """

    def __init__(self, analysis: AnalysisResult, *, line_length: int = 99) -> None:
        self._analysis = analysis
        self._line_length = line_length
        self._lines: list[str] = list()
        self._mappings: list[SourceMapping] = list()
        self._entry_map: dict[str, Any] = dict()

        for component in analysis.components:
            self._entry_map[component.config_path] = component
        for plain in analysis.plains:
            self._entry_map[plain.config_path] = plain
        for component in analysis.components:
            self._entry_map[component.var_name] = component
        for plain in analysis.plains:
            self._entry_map[plain.var_name] = plain

    def generate(
        self,
        call_target: str | None = None,
        call_method: str | None = None,
        call_args: list[Any] | None = None,
    ) -> tuple[str, list[SourceMapping]]:
        """
        Generate the full source code.
        """
        needs_asyncio = call_target is not None and self._is_async_call(
            call_target, call_method
        )
        self._emit_header(needs_asyncio=needs_asyncio)
        self._emit_imports()
        self._emit_blank()
        self._emit_entries()
        if call_target is not None:
            self._emit_blank()
            self._emit_call(call_target, call_method, call_args or [])
        return "\n".join(self._lines) + "\n", list(self._mappings)

    def _emit(self, line: str, config_path: str | None = None) -> None:
        """
        Emit a line of code, optionally recording its config path.
        """
        self._lines.append(line)
        if config_path is not None:
            mapping = SourceMapping(line=len(self._lines), config_path=config_path)
            self._mappings.append(mapping)

    def _emit_blank(self) -> None:
        self._lines.append("")

    def _emit_header(self, *, needs_asyncio: bool = False) -> None:
        self._emit("# Auto-generated by sygaldry for type checking — do not edit")
        if needs_asyncio:
            self._emit("import asyncio")
        self._emit("from typing import Any")

    def _emit_imports(self) -> None:
        seen: set[str] = set()
        for _, (mod, name) in sorted(self._analysis.imports.items(), key=lambda x: x[0]):
            statement = f"from {mod} import {name}"
            if statement not in seen:
                seen.add(statement)
                self._emit(statement)

    def _emit_entries(self) -> None:
        """
        Emit all entries in topological order.
        """
        emitted: set[str] = set()
        for config_path in self._analysis.topological_order:
            if config_path in emitted:
                continue
            entry = self._entry_map.get(config_path)
            if entry is None:
                continue

            emitted.add(config_path)

            if isinstance(entry, ComponentEntry):
                self._emit_component(entry)
            elif isinstance(entry, PlainEntry):
                self._emit_plain(entry)

    def _is_async_call(self, target: str, method: str | None) -> bool:
        """
        Check whether the call target's method (or __call__) is async.
        """
        entry = self._entry_map.get(target)
        if not isinstance(entry, ComponentEntry):
            return False
        try:
            mod_path, cls_name = _split_import_path(entry.import_path)
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            if method:
                func = getattr(cls, method, None)
            else:
                func = getattr(cls, "__call__", None)
            return inspect.iscoroutinefunction(func)
        except Exception:
            return False

    def _emit_call(
        self,
        target: str,
        method: str | None,
        args: list[Any],
    ) -> None:
        """
        Emit a call expression at the end of the generated code.
        """
        var_name = _to_identifier(target)
        if entry := self._entry_map.get(target):
            if isinstance(entry, (ComponentEntry, PlainEntry)):
                var_name = entry.var_name

        is_async = self._is_async_call(target, method)

        callee = f"{var_name}.{method}" if method else var_name
        arg_parts = [self._value_to_source(arg) for arg in args]
        args_str = ", ".join(arg_parts)
        call_expr = f"{callee}({args_str})"

        if is_async:
            one_line = f"asyncio.run({call_expr})"
            if len(one_line) <= self._line_length or not arg_parts:
                self._emit(one_line)
            else:
                self._emit(f"asyncio.run({callee}(")
                for idx, arg_part in enumerate(arg_parts):
                    suffix = "," if idx < len(arg_parts) - 1 else ""
                    self._emit(f"    {arg_part}{suffix}")
                self._emit("))")
        elif len(call_expr) <= self._line_length or not arg_parts:
            self._emit(call_expr)
        else:
            self._emit(f"{callee}(")
            for idx, arg_part in enumerate(arg_parts):
                suffix = "," if idx < len(arg_parts) - 1 else ""
                self._emit(f"    {arg_part}{suffix}")
            self._emit(")")

    def _emit_component(self, comp: ComponentEntry) -> None:
        """
        Emit a component (class instantiation or func import).
        """
        _, name = _split_import_path(comp.import_path)
        if comp.is_func:
            self._emit(
                f"{comp.var_name} = {name}  # config: {comp.config_path}",
                config_path=comp.config_path,
            )
            return

        parts = [self._value_to_source(arg) for arg in comp.args]
        for key, value in comp.kwargs.items():
            parts.append(f"{key}={self._value_to_source(value)}")

        comment = f"  # config: {comp.config_path}"
        args_str = ", ".join(parts)
        one_line = f"{comp.var_name}: {name} = {name}({args_str}){comment}"
        if len(one_line) <= self._line_length or not parts:
            self._emit(one_line, config_path=comp.config_path)
        else:
            self._emit(
                f"{comp.var_name}: {name} = {name}({comment}", config_path=comp.config_path
            )
            for part in parts:
                self._emit(f"    {part},")
            self._emit(")")

    def _emit_plain(self, plain: PlainEntry) -> None:
        """
        Emit a plain value assignment.
        """
        comment = f"  # config: {plain.config_path}"
        if isinstance(plain.value, RefExpression):
            target = self._resolve_ref_source(plain.value.target)
            self._emit(
                f"{plain.var_name} = {target}{comment}",
                config_path=plain.config_path,
            )
        elif plain.value is ...:
            self._emit(
                f"{plain.var_name}: Any = ...{comment}",
                config_path=plain.config_path,
            )
        elif isinstance(plain.value, EntriesExpression):
            items = [
                (self._value_to_source(key), self._value_to_source(value))
                for key, value in plain.value.items
            ]
            items_str = ", ".join(f"{k}: {v}" for k, v in items)
            one_line = f"{plain.var_name}: dict = {{{items_str}}}{comment}"
            if len(one_line) <= self._line_length or not items:
                self._emit(one_line, config_path=plain.config_path)
            else:
                self._emit(
                    f"{plain.var_name}: dict = {{{comment}", config_path=plain.config_path
                )
                for i, (k, v) in enumerate(items):
                    suffix = ","
                    self._emit(f"    {k}: {v}{suffix}")
                self._emit("}")
        else:
            type_name = self._python_type_name(plain.value)
            self._emit(
                f"{plain.var_name}: {type_name} = {self._value_to_source(plain.value)}{comment}",
                config_path=plain.config_path,
            )

    def _resolve_ref_source(self, target: str) -> str:
        """
        Convert a ref target to a Python expression.
        """
        top, _, remainder = target.partition(".")
        if entry := self._entry_map.get(top):
            if isinstance(entry, (ComponentEntry, PlainEntry)):
                var_name = entry.var_name
            else:
                var_name = _to_identifier(top)
        else:
            var_name = _to_identifier(top)
        if remainder:
            return f"{var_name}.{remainder}"
        return var_name

    def _value_to_source(self, value: Any) -> str:
        """
        Convert a config value to its Python source representation.
        """
        if isinstance(value, RefExpression):
            return self._resolve_ref_source(value.target)
        elif isinstance(value, EntriesExpression):
            items_str = ", ".join(
                f"{self._value_to_source(k)}: {self._value_to_source(v)}"
                for k, v in value.items
            )
            return f"{{{items_str}}}"
        elif value is ...:
            return "..."
        elif value is None:
            return "None"
        elif isinstance(value, bool):
            return "True" if value else "False"
        elif isinstance(value, (float, int, str)):
            return repr(value)
        elif isinstance(value, list):
            items = ", ".join(self._value_to_source(v) for v in value)
            return f"[{items}]"
        elif isinstance(value, dict):
            items = ", ".join(
                f"{self._value_to_source(k)}: {self._value_to_source(v)}"
                for k, v in value.items()
            )
            return f"{{{items}}}"
        else:
            return repr(value)

    @staticmethod
    def _python_type_name(value: Any) -> str:
        """
        Get a type annotation name for a plain value.
        """
        if value is None:
            return "None"
        elif isinstance(value, bool):
            return "bool"
        elif isinstance(value, int):
            return "int"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "str"
        elif isinstance(value, list):
            return "list"
        elif isinstance(value, dict):
            return "dict"
        else:
            return "Any"


def generate_check_source(
    config: dict[str, Any],
    *,
    line_length: int = 99,
    call_target: str | None = None,
    call_method: str | None = None,
    call_args: list[Any] | None = None,
) -> tuple[str, list[SourceMapping]]:
    """
    Generate type-checkable Python source from a sygaldry config.

    :param config: Loaded, interpolated config mapping.
    :param line_length: Maximum line length for generated code.
    :param call_target: Top-level config key to emit a call expression for.
    :param call_method: Method name to call on the target.
    :param call_args: Arguments for the call expression.
    :type config: dict
    :type line_length: int
    :returns: ``(source_code, mappings)`` tuple.
    """
    analyzer = ConfigAnalyzer(config)
    result = analyzer.analyze()
    generator = CodeGenerator(result, line_length=line_length)
    return generator.generate(
        call_target=call_target,
        call_method=call_method,
        call_args=call_args,
    )
