from __future__ import annotations

__author__ = "Rohan B. Dalton"

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .codegen import SourceMapping, generate_check_source
from .loader import load_config

SUPPORTED_CHECKERS = ("ty", "basedpyright", "pyright", "mypy")


@dataclass(frozen=True)
class CheckError:
    """
    A type error found in a config file.
    """

    config_path: str
    message: str
    severity: str = "error"


def check(
    path: str | Path | None = None,
    *,
    type_checker: str | None = None,
    config: dict[str, Any] | None = None,
) -> list[CheckError]:
    """
    Type check a sygaldry config file.

    Either *path* or *config* must be provided.  When *config* is given
    the config dict is used directly (useful from the CLI after loading
    and applying overrides).  When *path* is given, the file is loaded
    via :func:`load_config`.

    :param path: Path to a YAML/TOML config file.
    :param type_checker: Which checker to run (``ty``, ``basedpyright``,
        ``pyright``, or ``mypy``).  Auto-detected when *None*.
    :param config: Pre-loaded config dict.
    :returns: List of type errors found.
    """
    if config is None:
        if path is None:
            raise ValueError("Either path or config must be provided.")
        else:
            config = load_config(Path(path))

    source, mappings = generate_check_source(config)

    checker = type_checker or _detect_type_checker()
    return _run_and_parse(checker, source, mappings)


def _detect_type_checker() -> str:
    """
    Auto-detect an available type checker.
    """
    for name in SUPPORTED_CHECKERS:
        if shutil.which(name):
            return name
    raise RuntimeError("No supported type checker found. Install ty, basedpyright, pyright, or mypy.")


def _run_and_parse(
    checker: str,
    source: str,
    mappings: list[SourceMapping],
) -> list[CheckError]:
    """
    Write source to a temp file, run the checker, and parse results.
    """
    fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="_sygaldry_check_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(source)
        result = _invoke_checker(checker, tmp_path)
        return _parse_output(checker, result, mappings)
    finally:
        os.unlink(tmp_path)


def _invoke_checker(checker: str, filepath: str) -> subprocess.CompletedProcess:
    """
    Run the type checker subprocess.
    """
    if checker in ("pyright", "basedpyright"):
        cmd = [checker, "--outputjson", filepath]
    elif checker == "mypy":
        cmd = ["mypy", "--no-color-output", "--show-column-numbers", filepath]
    elif checker == "ty":
        cmd = ["ty", "check", filepath]
    else:
        raise ValueError(f"Unsupported type checker: {checker}")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _parse_output(
    checker: str,
    result: subprocess.CompletedProcess,
    mappings: list[SourceMapping],
) -> list[CheckError]:
    """
    Parse type checker output into CheckError instances.
    """
    if checker in ("pyright", "basedpyright"):
        return _parse_pyright(result, mappings)
    elif checker == "mypy":
        return _parse_mypy(result, mappings)
    elif checker == "ty":
        return _parse_ty(result, mappings)
    return list()


def _line_to_config_path(line: int, mappings: list[SourceMapping]) -> str:
    """
    Map a generated line number to its config path.
    """
    best: SourceMapping | None = None
    for mapping in mappings:
        if best is None or best.line < mapping.line <= line:
            best = mapping
    return best.config_path if best else "<unknown>"


def _parse_pyright(
    result: subprocess.CompletedProcess,
    mappings: list[SourceMapping],
) -> list[CheckError]:
    errors: list[CheckError] = list()
    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return errors
    for diag in data.get("generalDiagnostics", list()):
        line = diag.get("range", {}).get("start", {}).get("line", 0)
        # pyright uses 0-based lines
        config_path = _line_to_config_path(line + 1, mappings)
        severity = diag.get("severity", "error")
        message = diag.get("message", "")
        errors.append(
            CheckError(
                config_path=config_path,
                message=message,
                severity=severity,
            )
        )
    return errors


_MYPY_PATTERN = re.compile(
    r"^.+?:(?P<line>\d+):\d+:\s*(?P<severity>error|warning|note):\s*(?P<message>.+?)(?:\s+\[.+\])?$"
)


def _parse_mypy(
    result: subprocess.CompletedProcess,
    mappings: list[SourceMapping],
) -> list[CheckError]:
    errors: list[CheckError] = list()
    for raw_line in result.stdout.splitlines():
        match = _MYPY_PATTERN.match(raw_line)
        if not match:
            continue
        line_no = int(match.group("line"))
        severity = match.group("severity")
        message = match.group("message")
        if severity == "note":
            continue
        config_path = _line_to_config_path(line_no, mappings)
        errors.append(
            CheckError(
                config_path=config_path,
                message=message,
                severity=severity,
            )
        )
    return errors


_TY_LINE_PATTERN = re.compile(r"^\s*-->\s*.+?:(?P<line>\d+):\d+")
_TY_DIAG_PATTERN = re.compile(r"^(?P<severity>error|warning)\[.+?\]:\s*(?P<message>.+)")


def _parse_ty(
    result: subprocess.CompletedProcess,
    mappings: list[SourceMapping],
) -> list[CheckError]:
    errors: list[CheckError] = list()
    output = result.stdout + result.stderr
    lines = output.splitlines()

    for idx, line in enumerate(lines):
        if diag_match := _TY_DIAG_PATTERN.match(line):
            severity = diag_match.group("severity")
            message = diag_match.group("message")
            line_no = _extract_ty_line(lines, idx)
            config_path = _line_to_config_path(line_no, mappings) if line_no else "<unknown>"
            errors.append(
                CheckError(
                    config_path=config_path,
                    message=message,
                    severity=severity,
                )
            )

    return errors


def _extract_ty_line(lines: list[str], diag_idx: int) -> int | None:
    """
    Look ahead from a ty diagnostic line to find the --> line number.
    """
    for idx in range(diag_idx + 1, min(diag_idx + 6, len(lines))):
        if match := _TY_LINE_PATTERN.match(lines[idx]):
            return int(match.group("line"))
    return None
