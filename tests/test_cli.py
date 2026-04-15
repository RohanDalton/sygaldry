from __future__ import annotations

import pytest

from sygaldry.artificery import Artificery, _set_by_path
from sygaldry.cli import (
    _extract_call_defaults,
    _invoke_target,
    _parse_method_args,
    _parse_set_option,
    _parse_use_option,
)
from sygaldry.errors import CLIError, ConfigReferenceError


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


def test_artificery_overrides_set_simple(tmp_path):
    """
    GIVEN: A config file.
    WHEN:  Applying a set override via Artificery.
    THEN:  The target value is overridden.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("db:\n  host: localhost\n", encoding="utf-8")
    art = Artificery(cfg, overrides={"db.host": "prod-db"})
    assert art.config["db"]["host"] == "prod-db"


def test_artificery_overrides_set_nested_creates_path(tmp_path):
    """
    GIVEN: An empty config file.
    WHEN:  Applying a set override with a new nested path.
    THEN:  Intermediate dicts are created.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("{}\n", encoding="utf-8")
    art = Artificery(cfg, overrides={"new.nested.key": 42})
    assert art.config["new"]["nested"]["key"] == 42


def test_artificery_uses_copies_value(tmp_path):
    """
    GIVEN: A config with a defaults section.
    WHEN:  Applying a use mapping via Artificery.
    THEN:  The source value is copied to the target path.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "defaults:\n  prod_host: prod-db\ndb:\n  host: localhost\n",
        encoding="utf-8",
    )
    art = Artificery(cfg, uses={"db.host": "defaults.prod_host"})
    assert art.config["db"]["host"] == "prod-db"


def test_artificery_uses_missing_source_raises(tmp_path):
    """
    GIVEN: A config without the use source path.
    WHEN:  Preparing the config.
    THEN:  A ConfigReferenceError is raised.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("db:\n  host: localhost\n", encoding="utf-8")
    with pytest.raises(ConfigReferenceError, match="not found"):
        _ = Artificery(cfg, uses={"db.host": "missing.path"}).config


def test_artificery_overrides_after_uses(tmp_path):
    """
    GIVEN: Both uses and overrides targeting the same key.
    WHEN:  Preparing the config.
    THEN:  The override value takes precedence.
    """
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "defaults:\n  host: use-host\ndb:\n  host: original\n",
        encoding="utf-8",
    )
    art = Artificery(
        cfg,
        overrides={"db.host": "set-host"},
        uses={"db.host": "defaults.host"},
    )
    assert art.config["db"]["host"] == "set-host"


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


class _AsyncCallableObj:
    async def __call__(self, *args):
        return "async_called", args

    async def greet(self, name="world"):
        return f"Hello async, {name}!"


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


def test_invoke_target_async_callable():
    """
    GIVEN: An object with an async __call__.
    WHEN:  Invoking without a method name.
    THEN:  The coroutine is awaited via asyncio.run.
    """
    obj = _AsyncCallableObj()
    result = _invoke_target(obj, None, [])
    assert result == ("async_called", ())


def test_invoke_target_async_callable_with_args():
    """
    GIVEN: An object with an async __call__ and positional args.
    WHEN:  Invoking without a method name.
    THEN:  The args are passed and the coroutine is awaited.
    """
    obj = _AsyncCallableObj()
    result = _invoke_target(obj, None, [1, "two"])
    assert result == ("async_called", (1, "two"))


def test_invoke_target_async_named_method():
    """
    GIVEN: An object with an async named method.
    WHEN:  Invoking with the method name and args.
    THEN:  The coroutine is awaited and the result returned.
    """
    obj = _AsyncCallableObj()
    result = _invoke_target(obj, "greet", ["Alice"])
    assert result == "Hello async, Alice!"


if __name__ == "__main__":
    pass
