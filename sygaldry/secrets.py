"""Secret markers and safe representations for diagnostics and generated source."""

from __future__ import annotations

__author__ = "Rohan B. Dalton"

import re
from dataclasses import dataclass
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"password|passwd|secret|token|credential|api[_-]?key|private[_-]?key|"
    r"access[_-]?key|authorization|connection[_-]?string|^dsn$",
    re.IGNORECASE,
)
_REDACTED = "<redacted>"


@dataclass(frozen=True, repr=False, eq=False)
class Secret:
    """Keep a value private in config displays; constructors receive its actual value."""

    value: Any
    __hash__ = None

    def __eq__(self, other: Any) -> bool:
        result = self.value == reveal(other)
        return result

    def __repr__(self) -> str:
        result = _REDACTED
        return result

    def __str__(self) -> str:
        result = _REDACTED
        return result


def protect_secrets(value: Any, *, sensitive: bool = False) -> Any:
    """Recognize explicit markers and common credential names without losing types."""
    if isinstance(value, Secret):
        result = value
    elif isinstance(value, dict):
        if set(value) == {"_secret"}:
            result = Secret(reveal(value["_secret"]))
        else:
            result = {
                key: child
                if key in {"_type", "_func", "_ref", "_instance", "_lifecycle"}
                else protect_secrets(
                    child, sensitive=sensitive or bool(_SENSITIVE_KEY.search(str(key)))
                )
                for key, child in value.items()
            }
    elif isinstance(value, (list, tuple)):
        children = [protect_secrets(child, sensitive=sensitive) for child in value]
        result = tuple(children) if isinstance(value, tuple) else children
    elif sensitive:
        result = Secret(value)
    else:
        result = value
    return result


def reveal(value: Any) -> Any:
    """Unwrap markers only at execution boundaries."""
    if isinstance(value, Secret):
        result = reveal(value.value)
    elif isinstance(value, dict):
        result = {key: reveal(child) for key, child in value.items()}
    elif isinstance(value, list):
        result = [reveal(child) for child in value]
    elif isinstance(value, tuple):
        result = tuple(reveal(child) for child in value)
    else:
        result = value
    return result


def redact(value: Any) -> Any:
    """Produce printable data without calling application objects' repr methods."""
    if isinstance(value, Secret):
        result = _REDACTED
    elif isinstance(value, dict):
        result = {key: redact(child) for key, child in value.items()}
    elif isinstance(value, (list, tuple)):
        result = [redact(child) for child in value]
    elif value is None or isinstance(value, (str, bool, int, float)):
        result = value
    else:
        result = f"<{type(value).__name__}>"
    return result


def _placeholder(value: Any) -> Any:
    if value is None:
        result = None
    elif isinstance(value, bool):
        result = False
    elif isinstance(value, int):
        result = 0
    elif isinstance(value, float):
        result = 0.0
    elif isinstance(value, str):
        result = _REDACTED
    elif isinstance(value, dict):
        result = {key: _placeholder(child) for key, child in value.items()}
    elif isinstance(value, list):
        result = [_placeholder(child) for child in value]
    else:
        result = ...
    return result


def safe_codegen_data(value: Any) -> Any:
    """Replace secret literals with harmless values of the same primitive type."""
    protected = protect_secrets(value)
    if isinstance(protected, Secret):
        result = _placeholder(protected.value)
    elif isinstance(protected, dict):
        result = {key: safe_codegen_data(child) for key, child in protected.items()}
    elif isinstance(protected, list):
        result = [safe_codegen_data(child) for child in protected]
    elif isinstance(protected, tuple):
        result = tuple(safe_codegen_data(child) for child in protected)
    else:
        result = protected
    return result


def _secret_values(value: Any) -> list[Any]:
    if isinstance(value, Secret):
        unwrapped = reveal(value)
        if isinstance(unwrapped, (dict, list, tuple)):
            children = unwrapped.values() if isinstance(unwrapped, dict) else unwrapped
            values = [item for child in children for item in _secret_values(Secret(child))]
        else:
            values = [unwrapped]
    elif isinstance(value, dict):
        values = [item for child in value.values() for item in _secret_values(child)]
    elif isinstance(value, (list, tuple)):
        values = [item for child in value for item in _secret_values(child)]
    else:
        values = list()
    return values


def safe_display(value: Any, config: Any) -> Any:
    """Mask values derived from secrets, including references into the resolved graph."""
    literals = _secret_values(config)

    def display(child: Any) -> Any:
        if isinstance(child, Secret):
            result = _REDACTED
        elif isinstance(child, dict):
            result = {key: display(item) for key, item in child.items()}
        elif isinstance(child, (list, tuple)):
            result = [display(item) for item in child]
        elif isinstance(child, str):
            result = child
            for literal in literals:
                if isinstance(literal, str) and literal:
                    result = result.replace(literal, _REDACTED)
                else:
                    pass
        elif any(type(child) is type(literal) and child == literal for literal in literals):
            result = _REDACTED
        else:
            result = redact(child)
        return result

    result = display(protect_secrets(value))
    return result


if __name__ == "__main__":
    pass
