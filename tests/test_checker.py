__author__ = "Rohan B. Dalton"

import shutil

import pytest

from sygaldry.checker import CheckError, _detect_type_checker, check

_HAS_CHECKER = bool(
    shutil.which("ty")
    or shutil.which("basedpyright")
    or shutil.which("pyright")
    or shutil.which("mypy")
)
_skip_no_checker = pytest.mark.skipif(not _HAS_CHECKER, reason="No type checker available")


class Database:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port


class Service:
    def __init__(self, db: Database, url: str) -> None:
        self.db = db
        self.url = url


class Widget:
    def __init__(self, name: str, weight: float) -> None:
        self.name = name
        self.weight = weight


def test_check_error_defaults():
    """
    GIVEN: A CheckError with config_path and message.
    WHEN:  Inspecting its fields.
    THEN:  The severity defaults to "error" and fields are set.
    """
    err = CheckError(config_path="db", message="oops")
    assert err.severity == "error"
    assert err.config_path == "db"
    assert err.message == "oops"


def test_check_error_frozen():
    """
    GIVEN: A CheckError instance.
    WHEN:  Attempting to mutate a field.
    THEN:  An AttributeError is raised.
    """
    err = CheckError(config_path="db", message="oops")
    with pytest.raises(AttributeError):
        err.config_path = "other"


def test_detect_type_checker_returns_string():
    """
    GIVEN: A system with a type checker installed.
    WHEN:  Detecting the type checker.
    THEN:  One of the supported checker names is returned.
    """
    if _HAS_CHECKER:
        name = _detect_type_checker()
        assert name in ("ty", "basedpyright", "pyright", "mypy")


@_skip_no_checker
def test_valid_config_no_errors(tmp_path):
    """
    GIVEN: A valid YAML config with correct types.
    WHEN:  Running the type checker.
    THEN:  No errors are reported.
    """
    config_file = tmp_path / "valid.yaml"
    config_file.write_text(
        'db:\n  _type: "tests.test_checker.Database"\n  host: "localhost"\n  port: 5432\n',
        encoding="utf-8",
    )
    errors = check(config_file)
    assert errors == list()


@_skip_no_checker
def test_valid_config_with_ref(tmp_path):
    """
    GIVEN: A valid YAML config with _type and _ref entries.
    WHEN:  Running the type checker.
    THEN:  No errors are reported.
    """
    config_file = tmp_path / "valid_ref.yaml"
    config_file.write_text(
        "db:\n"
        '  _type: "tests.test_checker.Database"\n'
        '  host: "localhost"\n'
        "  port: 5432\n"
        "service:\n"
        '  _type: "tests.test_checker.Service"\n'
        '  db: { _ref: "db" }\n'
        '  url: "postgres://localhost:5432/app"\n',
        encoding="utf-8",
    )
    errors = check(config_file)
    assert errors == list()


@_skip_no_checker
def test_wrong_arg_type(tmp_path):
    """
    GIVEN: A config with an argument of the wrong type.
    WHEN:  Running the type checker.
    THEN:  At least one error is reported for the config path.
    """
    config_file = tmp_path / "wrong_type.yaml"
    config_file.write_text(
        'db:\n  _type: "tests.test_checker.Database"\n  host: 12345\n  port: 5432\n',
        encoding="utf-8",
    )
    errors = check(config_file)
    assert len(errors) > 0
    assert any("db" in e.config_path for e in errors)


@_skip_no_checker
def test_wrong_arg_name(tmp_path):
    """
    GIVEN: A config with a nonexistent constructor parameter.
    WHEN:  Running the type checker.
    THEN:  At least one error is reported.
    """
    config_file = tmp_path / "wrong_name.yaml"
    config_file.write_text(
        'w:\n  _type: "tests.test_checker.Widget"\n  name: "gizmo"\n  nonexistent_param: 42\n',
        encoding="utf-8",
    )
    errors = check(config_file)
    assert len(errors) > 0


@_skip_no_checker
def test_ref_type_mismatch(tmp_path):
    """
    GIVEN: A config where a _ref points to an incompatible type.
    WHEN:  Running the type checker.
    THEN:  At least one error is reported for the referencing config path.
    """
    config_file = tmp_path / "ref_mismatch.yaml"
    config_file.write_text(
        "w:\n"
        '  _type: "tests.test_checker.Widget"\n'
        '  name: "gizmo"\n'
        "  weight: 1.5\n"
        "service:\n"
        '  _type: "tests.test_checker.Service"\n'
        '  db: { _ref: "w" }\n'
        '  url: "http://example.com"\n',
        encoding="utf-8",
    )
    errors = check(config_file)
    assert len(errors) > 0
    assert any("service" in e.config_path for e in errors)


@_skip_no_checker
def test_preloaded_config():
    """
    GIVEN: A valid config dict passed directly.
    WHEN:  Running the type checker.
    THEN:  No errors are reported.
    """
    config = {
        "db": {
            "_type": "tests.test_checker.Database",
            "host": "localhost",
            "port": 5432,
        }
    }
    errors = check(config=config)
    assert errors == list()


@_skip_no_checker
def test_preloaded_config_with_error():
    """
    GIVEN: A config dict with an argument of the wrong type.
    WHEN:  Running the type checker.
    THEN:  At least one error is reported.
    """
    config = {
        "db": {
            "_type": "tests.test_checker.Database",
            "host": 12345,
            "port": 5432,
        }
    }
    errors = check(config=config)
    assert len(errors) > 0


@_skip_no_checker
def test_config_path_in_errors(tmp_path):
    """
    GIVEN: A config that produces type errors.
    WHEN:  Running the type checker.
    THEN:  All errors have a mapped config path (not "<unknown>").
    """
    config_file = tmp_path / "mapping.yaml"
    config_file.write_text(
        'db:\n  _type: "tests.test_checker.Database"\n  host: 999\n  port: 5432\n',
        encoding="utf-8",
    )
    errors = check(config_file)
    assert len(errors) > 0
    assert all(e.config_path != "<unknown>" for e in errors)


def test_check_requires_input_no_path_no_config():
    """
    GIVEN: Neither a file path nor a config dict.
    WHEN:  Calling check().
    THEN:  A ValueError is raised.
    """
    with pytest.raises(ValueError, match="Either path or config"):
        check()
