from __future__ import annotations

__author__ = "Rohan B. Dalton"

import json
from pathlib import Path
from typing import Any, Optional

import rich_click as click
import yaml
from rich.console import Console
from rich.syntax import Syntax

from .artificery import Artificery
from .checker import check as run_check
from .errors import CLIError, SygaldryError
from .loader import _infer_scalar

_console = Console(stderr=True)


def _parse_set_option(raw: str) -> tuple[str, Any]:
    """
    Parse a ``--set key=value`` string.

    :param raw: Raw option string.
    :type raw: str
    :returns: ``(dotted_path, coerced_value)`` pair.
    :raises CLIError: If the string has no ``=``.
    """
    if "=" not in raw:
        raise CLIError(f"Invalid --set syntax (expected key=value): '{raw}'")
    else:
        key, _, value = raw.partition("=")
        if key := key.strip():
            return key, _infer_scalar(value)
        else:
            raise CLIError(f"Invalid --set syntax (empty key): '{raw}'")


def _parse_use_option(raw: str) -> tuple[str, str]:
    """
    Parse a ``--use target=source`` string.

    :param raw: Raw option string.
    :type raw: str
    :returns: ``(target_path, source_path)`` pair.
    :raises CLIError: If the string has no ``=``.
    """
    if "=" not in raw:
        raise CLIError(f"Invalid --use syntax (expected target=source): '{raw}'")
    target, _, source = raw.partition("=")
    target = target.strip()
    source = source.strip()
    if not target or not source:
        raise CLIError(f"Invalid --use syntax (empty path): '{raw}'")
    return target, source


def _build_artificery(
    config_paths: tuple[Path, ...],
    set_overrides: tuple[str, ...],
    use_overrides: tuple[str, ...],
    *,
    cache: Any | None = None,
    transient: bool = False,
) -> Artificery:
    """
    Build an Artificery from CLI options.

    :param config_paths: Config file paths.
    :param set_overrides: ``--set`` option values.
    :param use_overrides: ``--use`` option values.
    :param cache: Optional instance cache.
    :param transient: If True, bypass caching.
    :returns: Configured Artificery instance.
    """
    overrides: dict[str, Any] = dict()
    for raw in set_overrides:
        key, value = _parse_set_option(raw)
        overrides[key] = value

    uses: dict[str, str] = dict()
    for raw in use_overrides:
        target, source = _parse_use_option(raw)
        uses[target] = source

    return Artificery(
        *config_paths,
        overrides=overrides or None,
        uses=uses or None,
        cache=cache,
        transient=transient,
    )


def _extract_call_defaults(
    config: dict[str, Any], object_key: str
) -> tuple[str | None, list[Any]]:
    """
    Extract ``_call`` defaults from the interpolated config.

    :param config: Interpolated (pre-resolution) config.
    :param object_key: Top-level key for the target object.
    :type config: dict
    :type object_key: str
    :returns: ``(method_name_or_None, args_list)`` pair.
    """
    obj_config = config.get(object_key)
    if not isinstance(obj_config, dict):
        return None, list()
    call = obj_config.get("_call")
    if not isinstance(call, dict):
        return None, list()
    method = call.get("method")
    args = call.get("args", [])
    if not isinstance(args, list):
        args = [args]
    return method, args


def _parse_method_args(raw_args: tuple[str, ...]) -> list[Any]:
    """
    Parse and coerce method arguments from CLI.

    :param raw_args: Raw argument strings from after ``--``.
    :type raw_args: tuple[str, ...]
    :returns: Coerced argument list.
    """
    return [_infer_scalar(arg) for arg in raw_args]


def _invoke_target(obj: Any, method_name: str | None, args: list[Any]) -> Any:
    """
    Call a method or the object itself.

    :param obj: Resolved target object.
    :param method_name: Method to call, or None for ``__call__``.
    :param args: Positional arguments.
    :type obj: object
    :type method_name: str | None
    :type args: list
    :returns: Return value of the call.
    :raises CLIError: If the object is not callable or method is missing.
    """
    if method_name is not None:
        if not hasattr(obj, method_name):
            raise CLIError(
                f"Object {type(obj).__name__!r} has no method '{method_name}'. "
                f"Available attributes: {sorted(a for a in dir(obj) if not a.startswith('_'))}"
            )
        target = getattr(obj, method_name)
        if not callable(target):
            raise CLIError(
                f"Attribute '{method_name}' on {type(obj).__name__!r} is not callable."
            )
        return target(*args)

    if not callable(obj):
        raise CLIError(
            f"Object {type(obj).__name__!r} is not callable and no --method was specified."
        )
    return obj(*args)


def _format_config_yaml(config: Any) -> str:
    """
    Format a config mapping as YAML.

    :param config: Config mapping to format.
    :type config: object
    :returns: YAML string.
    """
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _print_dry_run(
    config_paths: tuple[Path, ...],
    object_key: str,
    method_name: str | None,
    args: list[Any],
    config: dict[str, Any],
) -> None:
    """Print a dry-run summary.

    :param config_paths: Config file paths that were loaded.
    :param object_key: Object key to resolve.
    :param method_name: Method to call.
    :param args: Method arguments.
    :param config: Interpolated config.
    """
    _console.print("[bold]Dry run summary[/bold]")
    _console.print()
    _console.print(f"  Config files: {', '.join(str(p) for p in config_paths)}")
    _console.print(f"  Object:       {object_key}")

    call_desc = method_name or "__call__"
    _console.print(f"  Method:       {call_desc}")

    if args:
        _console.print(f"  Args:         {args}")
    else:
        _console.print("  Args:         (none)")

    obj_config = config.get(object_key, {})
    if isinstance(obj_config, dict):
        _console.print()
        _console.print(f"  [bold]Config for '{object_key}':[/bold]")
        yaml_str = _format_config_yaml(obj_config)
        syntax = Syntax(yaml_str, "yaml", theme="monokai", padding=1)
        _console.print(syntax)


def _config_options(func):
    """
    Shared options for config loading, --set, and --use.
    """
    func = click.option(
        "-c",
        "--config",
        "config_paths",
        multiple=True,
        required=True,
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
        envvar="SYGALDRY_CONFIG",
        help="Config file path. Repeat for multiple files; deep-merged in order.",
    )(func)
    func = click.option(
        "--set",
        "set_overrides",
        multiple=True,
        help="Override a config value: dotted.path=value.",
    )(func)
    func = click.option(
        "--use",
        "use_overrides",
        multiple=True,
        help="Set a config value from another config path: target.path=source.path.",
    )(func)
    return func


class _DefaultGroup(click.RichGroup):
    """
    Click group that defaults to the 'run' subcommand.
    """

    def parse_args(self, ctx, args):
        # If the first arg isn't a known subcommand, insert 'run'.
        if args and args[0] not in self.commands and not args[0].startswith("-"):
            # Not a known command and not a flag -- unknown arg, let Click handle it.
            pass
        elif args and args[0] not in self.commands:
            args = ["run"] + list(args)
        elif not args:
            args = ["run"]
        return super().parse_args(ctx, args)


@click.group(cls=_DefaultGroup)
@click.version_option(package_name="sygaldry")
def cli():
    """
    Sygaldry: build and run objects from config files.
    """


@cli.command(context_settings={"ignore_unknown_options": True})
@_config_options
@click.option(
    "--object",
    "object_key",
    required=True,
    help="Top-level config key to resolve and use.",
)
@click.option(
    "--method",
    "method_name",
    default=None,
    help="Method to call on the resolved object. Default: call the object itself.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate and show what would be called, without executing.",
)
@click.option("-v", "--verbose", is_flag=True, help="Show full tracebacks on error.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-error output.")
@click.argument("method_args", nargs=-1, type=click.UNPROCESSED)
def run(
    config_paths: tuple[Path, ...],
    set_overrides: tuple[str, ...],
    use_overrides: tuple[str, ...],
    object_key: str,
    method_name: str | None,
    dry_run: bool,
    verbose: bool,
    quiet: bool,
    method_args: tuple[str, ...],
) -> None:
    """
    Load config, resolve an object, and call it.
    """
    try:
        art = _build_artificery(config_paths, set_overrides, use_overrides)
        call_method, call_args = _extract_call_defaults(art.config, object_key)

        final_method = method_name if method_name is not None else call_method
        final_args = _parse_method_args(method_args) if method_args else call_args

        if dry_run:
            _print_dry_run(config_paths, object_key, final_method, final_args, art.config)
            return
        else:
            resolved = art.resolve()

            if object_key not in resolved:
                available = sorted(resolved.keys())
                raise CLIError(
                    f"Object '{object_key}' not found in resolved config. "
                    f"Available keys: {available}"
                )
            target = resolved[object_key]

            result = _invoke_target(target, final_method, final_args)

            if isinstance(result, int):
                raise SystemExit(result)
            if result is not None and not quiet:
                click.echo(result)

    except SystemExit:
        raise
    except SygaldryError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        if verbose:
            _console.print_exception()
        else:
            _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None


@cli.command()
@_config_options
@click.option(
    "--object",
    "object_key",
    default=None,
    help="Show only this top-level key.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["yaml", "json"]),
    default="yaml",
    help="Output format.",
)
@click.option(
    "--resolved",
    is_flag=True,
    help="Show resolved config (objects instantiated).",
)
@click.option(
    "--list-objects",
    is_flag=True,
    help="List available top-level config keys.",
)
def show(
    config_paths: tuple[Path, ...],
    set_overrides: tuple[str, ...],
    use_overrides: tuple[str, ...],
    object_key: str | None,
    output_format: str,
    resolved: bool,
    list_objects: bool,
) -> None:
    """Display the merged config for debugging."""
    try:
        art = _build_artificery(config_paths, set_overrides, use_overrides)

        if list_objects:
            for key in sorted(art.config.keys()):
                click.echo(key)
            return

        if resolved:
            output = art.resolve()
            if object_key:
                if object_key not in output:
                    available = sorted(output.keys())
                    raise CLIError(
                        f"Object '{object_key}' not found. Available keys: {available}"
                    )
                click.echo(repr(output[object_key]))
            else:
                for key, value in output.items():
                    click.echo(f"{key}: {repr(value)}")
            return

        display = art.config
        if object_key:
            if object_key not in display:
                available = sorted(display.keys())
                raise CLIError(f"Object '{object_key}' not found. Available keys: {available}")
            display = display[object_key]

        if output_format == "json":
            click.echo(json.dumps(display, indent=2, default=str))
        else:
            yaml_str = _format_config_yaml(display)
            syntax = Syntax(yaml_str, "yaml", theme="monokai")
            Console().print(syntax)

    except SystemExit:
        raise
    except SygaldryError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None


@cli.command()
@_config_options
def validate(
    config_paths: tuple[Path, ...],
    set_overrides: tuple[str, ...],
    use_overrides: tuple[str, ...],
) -> None:
    """Validate config without executing."""
    try:
        _build_artificery(config_paths, set_overrides, use_overrides).resolve()
        _console.print("[bold green]Config is valid.[/bold green]")

    except SygaldryError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None


@cli.command()
@_config_options
@click.option(
    "--type-checker",
    "type_checker",
    type=click.Choice(["ty", "basedpyright", "pyright", "mypy"]),
    default=None,
    help="Type checker to use (auto-detected if omitted).",
)
@click.option("-v", "--verbose", is_flag=True, help="Show full tracebacks on error.")
def check(
    config_paths: tuple[Path, ...],
    set_overrides: tuple[str, ...],
    use_overrides: tuple[str, ...],
    type_checker: str | None,
    verbose: bool,
) -> None:
    """
    Static type check a config file.
    """

    try:
        art = _build_artificery(config_paths, set_overrides, use_overrides)

        errors = run_check(config=art.config, type_checker=type_checker)

        if not errors:
            _console.print("[bold green]No type errors found.[/bold green]")
            return

        for err in errors:
            label = err.severity.upper()
            _console.print(f"[bold red]{label}:[/bold red] {err.config_path}: {err.message}")

        raise SystemExit(1)

    except SystemExit:
        raise
    except SygaldryError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        if verbose:
            _console.print_exception()
        else:
            _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None


@cli.command()
@_config_options
@click.option("-v", "--verbose", is_flag=True, help="Show full tracebacks on error.")
def interactive(
    config_paths: tuple[Path, ...],
    set_overrides: tuple[str, ...],
    use_overrides: tuple[str, ...],
    verbose: bool,
) -> None:
    """
    Start an interactive Python session with the Artificery loaded.
    """
    import code

    try:
        art = _build_artificery(config_paths, set_overrides, use_overrides)
        # Eagerly prepare the config so errors surface before the REPL starts.
        _ = art.config

    except SygaldryError as exc:
        _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None
    except Exception as exc:
        if verbose:
            _console.print_exception()
        else:
            _console.print(f"[bold red]Error:[/bold red] {exc}")
        raise SystemExit(1) from None

    banner_lines = [
        "Sygaldry interactive session",
        "",
        "Available variables:",
        "  artificery  - Artificery instance (config loaded & merged)",
        "",
        "Quick start:",
        "  artificery.config        # view the interpolated config",
        "  artificery.resolve()     # resolve all objects",
        "",
    ]
    banner = "\n".join(banner_lines)
    _console.print(f"[bold green]{banner_lines[0]}[/bold green]")
    _console.print()
    _console.print("  Config files: " + ", ".join(str(p) for p in config_paths))
    _console.print(f"  Top-level keys: {sorted(art.config.keys())}")
    _console.print()

    namespace: dict[str, Any] = {"artificery": art, "Artificery": Artificery}
    code.interact(banner=banner, local=namespace, exitmsg="")


if __name__ == "__main__":
    cli()
