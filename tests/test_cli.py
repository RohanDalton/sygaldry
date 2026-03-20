from __future__ import annotations

import pytest

from sygaldry.cli import (
    _apply_overrides,
    _extract_call_defaults,
    _invoke_target,
    _parse_method_args,
    _parse_set_option,
    _parse_use_option,
    _set_by_path,
)
from sygaldry.errors import CLIError


def test_set_by_path_simple_key():
    """
    GIVEN: A flat dict.
    WHEN:  Setting a simple key.
    THEN:  The value is set.
    """
    data = {"a": 1}
    _set_by_path(data, "b", 2)
    assert data == {"a": 1, "b": 2}


def test_set_by_path_nested_creates_intermediates():
    """
    GIVEN: An empty dict.
    WHEN:  Setting a nested path.
    THEN:  Intermediate dicts are created.
    """
    data = dict()
    _set_by_path(data, "a.b.c", 42)
    assert data == {"a": {"b": {"c": 42}}}


def test_set_by_path_overwrites_existing():
    """
    GIVEN: An existing nested value.
    WHEN:  Setting the same path.
    THEN:  The value is overwritten.
    """
    data = {"db": {"host": "localhost", "port": 5432}}
    _set_by_path(data, "db.host", "prod-db")
    assert data == {"db": {"host": "prod-db", "port": 5432}}


def test_set_by_path_overwrites_non_dict_intermediate():
    """
    GIVEN: A scalar at an intermediate path.
    WHEN:  Setting a deeper path.
    THEN:  The scalar is replaced with a dict.
    """
    data = {"a": "scalar"}
    _set_by_path(data, "a.b", 1)
    assert data == {"a": {"b": 1}}


def test_parse_set_option_string_value():
    """
    GIVEN: A key=value string.
    WHEN:  Parsing the --set option.
    THEN:  The key and string value are returned.
    """
    key, value = _parse_set_option("db.host=newhost")
    assert key == "db.host"
    assert value == "newhost"


def test_parse_set_option_int_coercion():
    """
    GIVEN: A key=int string.
    WHEN:  Parsing the --set option.
    THEN:  The value is coerced to int.
    """
    key, value = _parse_set_option("db.port=5433")
    assert key == "db.port"
    assert value == 5433


def test_parse_set_option_float_coercion():
    """
    GIVEN: A key=float string.
    WHEN:  Parsing the --set option.
    THEN:  The value is coerced to float.
    """
    key, value = _parse_set_option("rate=3.14")
    assert key == "rate"
    assert value == 3.14


def test_parse_set_option_bool_coercion():
    """
    GIVEN: A key=true string.
    WHEN:  Parsing the --set option.
    THEN:  The value is coerced to bool.
    """
    key, value = _parse_set_option("debug=true")
    assert key == "debug"
    assert value is True


def test_parse_set_option_none_coercion():
    """
    GIVEN: A key=null string.
    WHEN:  Parsing the --set option.
    THEN:  The value is coerced to None.
    """
    key, value = _parse_set_option("opt=null")
    assert key == "opt"
    assert value is None


def test_parse_set_option_no_equals_raises():
    """
    GIVEN: A string without an equals sign.
    WHEN:  Parsing the --set option.
    THEN:  A CLIError is raised.
    """
    with pytest.raises(CLIError, match="Invalid --set syntax"):
        _parse_set_option("noequals")


def test_parse_set_option_empty_key_raises():
    """
    GIVEN: A string with an empty key.
    WHEN:  Parsing the --set option.
    THEN:  A CLIError is raised.
    """
    with pytest.raises(CLIError, match="empty key"):
        _parse_set_option("=value")


def test_parse_set_option_value_with_equals():
    """
    GIVEN: A value containing an equals sign.
    WHEN:  Parsing the --set option.
    THEN:  Only the first equals sign is used as the split point.
    """
    key, value = _parse_set_option("url=http://host:8080/path?a=b")
    assert key == "url"
    assert value == "http://host:8080/path?a=b"


def test_parse_use_option_valid():
    """
    GIVEN: A valid target=source string.
    WHEN:  Parsing the --use option.
    THEN:  Both paths are returned.
    """
    target, source = _parse_use_option("db.host=defaults.production_host")
    assert target == "db.host"
    assert source == "defaults.production_host"


def test_parse_use_option_no_equals_raises():
    """
    GIVEN: A string without an equals sign.
    WHEN:  Parsing the --use option.
    THEN:  A CLIError is raised.
    """
    with pytest.raises(CLIError, match="Invalid --use syntax"):
        _parse_use_option("noequals")


def test_parse_use_option_empty_target_raises():
    """
    GIVEN: An empty target path.
    WHEN:  Parsing the --use option.
    THEN:  A CLIError is raised.
    """
    with pytest.raises(CLIError, match="empty path"):
        _parse_use_option("=source")


def test_parse_use_option_empty_source_raises():
    """
    GIVEN: An empty source path.
    WHEN:  Parsing the --use option.
    THEN:  A CLIError is raised.
    """
    with pytest.raises(CLIError, match="empty path"):
        _parse_use_option("target=")


def test_apply_overrides_set_simple():
    """
    GIVEN: A config dict.
    WHEN:  Applying a --set override.
    THEN:  The target value is overridden.
    """
    config = {"db": {"host": "localhost"}}
    result = _apply_overrides(config, sets=("db.host=prod-db",), uses=())
    assert result["db"]["host"] == "prod-db"


def test_apply_overrides_set_nested_creates_path():
    """
    GIVEN: An empty config dict.
    WHEN:  Applying a --set override with a new nested path.
    THEN:  Intermediate dicts are created.
    """
    config = dict()
    result = _apply_overrides(config, sets=("new.nested.key=42",), uses=())
    assert result["new"]["nested"]["key"] == 42


def test_apply_overrides_use_copies_value():
    """
    GIVEN: A config with a defaults section.
    WHEN:  Applying a --use override.
    THEN:  The source value is copied to the target path.
    """
    config = {"defaults": {"prod_host": "prod-db"}, "db": {"host": "localhost"}}
    result = _apply_overrides(config, sets=(), uses=("db.host=defaults.prod_host",))
    assert result["db"]["host"] == "prod-db"


def test_apply_overrides_use_missing_source_raises():
    """
    GIVEN: A config without the --use source path.
    WHEN:  Applying the override.
    THEN:  A CLIError is raised.
    """
    config = {"db": {"host": "localhost"}}
    with pytest.raises(CLIError, match="not found in config"):
        _apply_overrides(config, sets=(), uses=("db.host=missing.path",))


def test_apply_overrides_use_then_set_precedence():
    """
    GIVEN: Both --use and --set targeting the same key.
    WHEN:  Applying overrides.
    THEN:  The --set value takes precedence.
    """
    config = {"defaults": {"host": "use-host"}, "db": {"host": "original"}}
    result = _apply_overrides(
        config,
        sets=("db.host=set-host",),
        uses=("db.host=defaults.host",),
    )
    assert result["db"]["host"] == "set-host"


def test_parse_method_args_coercion():
    """
    GIVEN: A tuple of mixed type strings.
    WHEN:  Parsing method args.
    THEN:  Values are coerced to their native types.
    """
    result = _parse_method_args(("42", "hello", "true", "3.14", "null"))
    assert result == [42, "hello", True, 3.14, None]


def test_parse_method_args_empty():
    """
    GIVEN: An empty tuple.
    WHEN:  Parsing method args.
    THEN:  An empty list is returned.
    """
    assert _parse_method_args(()) == list()


def test_extract_call_defaults_with_method_and_args():
    """
    GIVEN: A config with a _call directive containing method and args.
    WHEN:  Extracting call defaults.
    THEN:  The method name and args are returned.
    """
    config = {
        "pipeline": {
            "_type": "myapp.Pipeline",
            "_call": {"method": "execute", "args": ["daily"]},
        }
    }
    method, args = _extract_call_defaults(config, "pipeline")
    assert method == "execute"
    assert args == ["daily"]


def test_extract_call_defaults_without_call_key():
    """
    GIVEN: A config without a _call directive.
    WHEN:  Extracting call defaults.
    THEN:  None and an empty list are returned.
    """
    config = {"pipeline": {"_type": "myapp.Pipeline"}}
    method, args = _extract_call_defaults(config, "pipeline")
    assert method is None
    assert args == list()


def test_extract_call_defaults_partial_only_method():
    """
    GIVEN: A _call directive with only a method and no args.
    WHEN:  Extracting call defaults.
    THEN:  The method is returned and args defaults to an empty list.
    """
    config = {"pipeline": {"_call": {"method": "run"}}}
    method, args = _extract_call_defaults(config, "pipeline")
    assert method == "run"
    assert args == list()


def test_extract_call_defaults_missing_object_key():
    """
    GIVEN: A config without the requested object key.
    WHEN:  Extracting call defaults.
    THEN:  Defaults are returned.
    """
    config = {"other": {}}
    method, args = _extract_call_defaults(config, "pipeline")
    assert method is None
    assert args == list()


def test_extract_call_defaults_non_dict_object():
    """
    GIVEN: A non-dict value at the object key.
    WHEN:  Extracting call defaults.
    THEN:  Defaults are returned.
    """
    config = {"pipeline": "just a string"}
    method, args = _extract_call_defaults(config, "pipeline")
    assert method is None
    assert args == list()


class _CallableObj:
    def __call__(self, *args):
        return "called", args

    @staticmethod
    def greet(name="world"):
        return f"Hello, {name}!"


class _NonCallableObj:
    value = 42


def test_invoke_target_callable_object():
    """
    GIVEN: A callable object.
    WHEN:  Invoking without a method name.
    THEN:  The __call__ method is used.
    """
    obj = _CallableObj()
    result = _invoke_target(obj, None, [])
    assert result == ("called", ())


def test_invoke_target_callable_with_args():
    """
    GIVEN: A callable object and positional args.
    WHEN:  Invoking without a method name.
    THEN:  The args are passed to __call__.
    """
    obj = _CallableObj()
    result = _invoke_target(obj, None, [1, "two"])
    assert result == ("called", (1, "two"))


def test_invoke_target_named_method():
    """
    GIVEN: An object with a named method.
    WHEN:  Invoking with the method name and args.
    THEN:  The method is called with the args.
    """
    obj = _CallableObj()
    result = _invoke_target(obj, "greet", ["Alice"])
    assert result == "Hello, Alice!"


def test_invoke_target_not_callable_raises():
    """
    GIVEN: A non-callable object.
    WHEN:  Invoking without a method name.
    THEN:  A CLIError is raised.
    """
    obj = _NonCallableObj()
    with pytest.raises(CLIError, match="not callable"):
        _invoke_target(obj, None, [])


def test_invoke_target_missing_method_raises():
    """
    GIVEN: An object without the requested method.
    WHEN:  Invoking with a nonexistent method name.
    THEN:  A CLIError is raised.
    """
    obj = _CallableObj()
    with pytest.raises(CLIError, match="has no method"):
        _invoke_target(obj, "nonexistent", [])


def test_invoke_target_non_callable_attribute_raises():
    """
    GIVEN: An object with a non-callable attribute.
    WHEN:  Invoking with that attribute as the method.
    THEN:  A CLIError is raised.
    """
    obj = _NonCallableObj()
    with pytest.raises(CLIError, match="not callable"):
        _invoke_target(obj, "value", [])


if __name__ == "__main__":
    pass
