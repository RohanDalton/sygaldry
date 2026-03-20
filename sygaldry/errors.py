from __future__ import annotations

__author__ = "Rohan B. Dalton"

from typing import Optional


class SygaldryError(Exception):
    """
    Base error for all Sygaldry failures.

    :param message: Human-readable error message.
    :param file_path: Source config file path, if known.
    :param config_path: Dotted config path for context.
    :type message: str
    :type file_path: str | None
    :type config_path: str | None
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        config_path: Optional[str] = None,
    ):
        super().__init__(message)
        self._message = message
        self._file_path = file_path
        self._config_path = config_path

    def __str__(self) -> str:
        """
        Render the error with optional file/config context.

        :returns: Formatted error string with file and config path context.
        :rtype: str
        """
        parts = list()
        if self._file_path:
            parts.append(f"file='{self._file_path}'")
        if self._config_path:
            parts.append(f"path='{self._config_path}'")
        if parts:
            return f"{self._message} ({', '.join(parts)})"
        return self._message


class LoadError(SygaldryError):
    """
    Errors during file loading or parsing.
    """


class ParseError(LoadError):
    """
    Parsing failures for YAML or TOML.
    """


class IncludeError(LoadError):
    """
    Errors during include resolution or deep merge.
    """


class CircularIncludeError(IncludeError):
    """
    Circular include detected.
    """


class ValidationError(SygaldryError):
    """
    Schema or config validation failures.
    """


class ConfigReferenceError(ValidationError):
    """
    Missing or invalid _ref targets.
    """


class CircularReferenceError(ConfigReferenceError):
    """
    Circular _ref detected.
    """


class InterpolationError(ValidationError):
    """
    Interpolation failures.
    """


class CircularInterpolationError(InterpolationError):
    """
    Circular interpolation detected.
    """


class ImportResolutionError(SygaldryError):
    """
    Import or dotted path resolution failures.
    """


class ResolutionError(SygaldryError):
    """
    Errors during recursive resolution.
    """


class ConstructorError(ResolutionError):
    """
    Constructor invocation failures.
    """


class ConfigConflictError(SygaldryError):
    """
    Cache conflicts for identical keys with differing specs.
    """


class CLIError(SygaldryError):
    """
    Errors originating from CLI argument processing.
    """


if __name__ == "__main__":
    pass
