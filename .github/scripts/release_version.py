"""Check a main-branch push for a releasable version increase without importing code."""

import ast
import os
import subprocess
from pathlib import Path

from packaging.version import Version

VERSION_FILE = "sygaldry/__version__.py"


def read_version(source: str) -> Version:
    """Read a single literal version assignment, without executing the module."""
    values = [
        ast.literal_eval(node.value)
        for node in ast.parse(source).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "__version__"
            for target in node.targets
        )
    ]
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError(f"{VERSION_FILE} must contain one literal __version__ string.")
    version = Version(values[0])
    if str(version) != values[0] or version.local is not None or version.epoch:
        raise ValueError("Use a canonical public version without an epoch or local suffix.")
    return version


def git(*args: str) -> str:
    """Read repository metadata, failing if the requested history is unavailable."""
    return subprocess.check_output(["git", *args], text=True).strip()  # noqa: S603, S607


def release_version(before: str, commit: str) -> Version | None:
    """Compare the complete push range, including squash and multi-commit pushes."""
    if not before or set(before) == {"0"}:
        raise ValueError("Cannot detect a version bump without the previous main commit.")
    previous = read_version(git("show", f"{before}:{VERSION_FILE}"))
    current = read_version(git("show", f"{commit}:{VERSION_FILE}"))
    if current == previous:
        return None
    if current < previous:
        raise ValueError(f"Version must increase: {previous} -> {current}.")
    tag = f"v{current}"
    if git("tag", "--list", tag):
        tagged_commit = git("rev-parse", f"refs/tags/{tag}^{{commit}}")
        if tagged_commit != git("rev-parse", commit):
            raise ValueError(f"Tag {tag} already belongs to another commit.")
    return current


def main() -> None:
    version = release_version(os.environ["BEFORE"], os.environ["COMMIT"])
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"changed={str(version is not None).lower()}\n")
        if version is not None:
            output.write(f"version={version}\n")
    print(f"Release v{version}" if version is not None else "Version unchanged; no release.")


if __name__ == "__main__":
    main()
