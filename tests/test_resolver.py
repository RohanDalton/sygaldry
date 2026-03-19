__author__ = "Rohan B. Dalton"

import math

import pytest

from sygaldry.errors import (
    CircularReferenceError,
    ConfigReferenceError,
    ValidationError,
)
from sygaldry.resolver import resolve_config


class Demo:
    def __init__(self, value, *, scale=1):
        self.value = value
        self.scale = scale


def test_resolve_type_and_ref():
    """
    GIVEN: A config with _type and _ref entries.
    WHEN:  Resolving the config.
    THEN:  References are resolved bottom-up.
    """
    config = {
        "base": {"_type": "tests.test_resolver.Demo", "_args": [3]},
        "wrapped": {"_type": "tests.test_resolver.Demo", "value": {"_ref": "base"}},
    }

    resolved = resolve_config(config)

    assert resolved["wrapped"].value is resolved["base"]


def test_resolve_func_returns_callable():
    """
    GIVEN: A config with a _func entry.
    WHEN:  Resolving the config.
    THEN:  The resolved value is a callable.
    """
    config = {"joiner": {"_func": "os.path.join"}}

    resolved = resolve_config(config)

    assert callable(resolved["joiner"])


def test_ref_dotted_attribute():
    """
    GIVEN: A config with a dotted _ref path.
    WHEN:  Resolving the config.
    THEN:  Attributes on the resolved object are followed.
    """
    config = {
        "demo": {"_type": "tests.test_resolver.Demo", "_args": [7], "scale": 2},
        "value": {"_ref": "demo.value"},
    }

    resolved = resolve_config(config)

    assert resolved["value"] == 7


def test_deep_false_returns_raw_dict():
    """
    GIVEN: A config dict with _deep set to false.
    WHEN:  Resolving the config.
    THEN:  Children are returned unresolved and the _deep key is stripped.
    """
    config = {
        "raw": {
            "_deep": False,
            "child": {"_type": "tests.test_resolver.Demo", "_args": [1]},
        }
    }

    resolved = resolve_config(config)

    assert resolved["raw"]["child"]["_type"] == "tests.test_resolver.Demo"
    assert "_deep" not in resolved["raw"]


def test_entries_resolves_keys_and_values():
    """
    GIVEN: A config with _entries containing refs and funcs.
    WHEN:  Resolving the config.
    THEN:  Both keys and values are resolved.
    """
    config = {
        "key": {"_type": "tests.test_resolver.Demo", "_args": [5]},
        "map": {
            "_entries": [
                {"_key": {"_ref": "key"}, "_value": {"_ref": "key.value"}},
                {"_key": "pi", "_value": {"_func": "math.sqrt"}},
            ]
        },
    }

    resolved = resolve_config(config)

    assert resolved["map"][resolved["key"]] == 5
    assert resolved["map"]["pi"] is math.sqrt


def test_missing_ref_raises():
    """
    GIVEN: A config with a _ref pointing to a missing target.
    WHEN:  Resolving the config.
    THEN:  A ConfigReferenceError is raised.
    """
    config = {"value": {"_ref": "missing"}}

    with pytest.raises(ConfigReferenceError):
        resolve_config(config)


def test_circular_ref_raises():
    """
    GIVEN: A config with circular _ref entries.
    WHEN:  Resolving the config.
    THEN:  A CircularReferenceError is raised.
    """
    config = {"a": {"_ref": "b"}, "b": {"_ref": "a"}}

    with pytest.raises(CircularReferenceError):
        resolve_config(config)


def test_func_extra_keys_raises():
    """
    GIVEN: A config with _func accompanied by extra keys.
    WHEN:  Resolving the config.
    THEN:  A ValidationError is raised mentioning the extra key.
    """
    config = {"fn": {"_func": "os.path.join", "extra": "oops"}}

    with pytest.raises(ValidationError, match="extra"):
        resolve_config(config)


def test_deep_ref_validation_catches_missing_nested_key():
    """
    GIVEN: A config with a _ref to a nested path that doesn't exist.
    WHEN:  Resolving the config.
    THEN:  A ConfigReferenceError is raised mentioning the missing segment.
    """
    config = {
        "db": {"host": "localhost", "port": 5432},
        "svc": {"_ref": "db.missing_key"},
    }

    with pytest.raises(ConfigReferenceError, match="missing_key"):
        resolve_config(config)


if __name__ == "__main__":
    pass
