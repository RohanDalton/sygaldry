__author__ = "Rohan B. Dalton"

import textwrap

from sygaldry.codegen import (
    CodeGenerator,
    ConfigAnalyzer,
    EntriesExpression,
    RefExpression,
    _split_import_path,
    _to_identifier,
    generate_check_source,
)


def _strip(source: str) -> str:
    """Normalize generated source for comparison."""
    return textwrap.dedent(source).strip()


def _source_for(config: dict) -> str:
    """Generate source from a config and return it stripped."""
    source, _ = generate_check_source(config)
    return source.strip()


def test_to_identifier_simple():
    """
    GIVEN: A simple alphabetic string.
    WHEN:  Converting to an identifier.
    THEN:  The string is returned unchanged.
    """
    assert _to_identifier("db") == "db"


def test_to_identifier_hyphen():
    """
    GIVEN: A string containing a hyphen.
    WHEN:  Converting to an identifier.
    THEN:  The hyphen is replaced with an underscore.
    """
    assert _to_identifier("my-service") == "my_service"


def test_to_identifier_leading_digit():
    """
    GIVEN: A string starting with a digit.
    WHEN:  Converting to an identifier.
    THEN:  An underscore is prepended.
    """
    assert _to_identifier("3d_model") == "_3d_model"


def test_to_identifier_dots():
    """
    GIVEN: A dotted path string.
    WHEN:  Converting to an identifier.
    THEN:  Dots are replaced with underscores.
    """
    assert _to_identifier("a.b.c") == "a_b_c"


def test_to_identifier_empty():
    """
    GIVEN: An empty string.
    WHEN:  Converting to an identifier.
    THEN:  A fallback name is returned.
    """
    assert _to_identifier("") == "_unnamed"


def test_split_import_path_dotted():
    """
    GIVEN: A dotted import path with module and attribute.
    WHEN:  Splitting the import path.
    THEN:  The module and attribute are separated.
    """
    assert _split_import_path("myapp.db.Database") == ("myapp.db", "Database")


def test_split_import_path_single():
    """
    GIVEN: A single-segment import path.
    WHEN:  Splitting the import path.
    THEN:  Both module and attribute are the same.
    """
    assert _split_import_path("builtins") == ("builtins", "builtins")


def test_split_import_path_two_parts():
    """
    GIVEN: A two-part dotted path.
    WHEN:  Splitting the import path.
    THEN:  The first part is the module, the second is the attribute.
    """
    assert _split_import_path("os.path") == ("os", "path")


def test_analyzer_type_entry():
    """
    GIVEN: A config with a single _type entry.
    WHEN:  Analyzing the config.
    THEN:  One component is produced with correct fields.
    """
    config = {
        "db": {
            "_type": "myapp.db.Database",
            "host": "localhost",
            "port": 5432,
        }
    }
    result = ConfigAnalyzer(config).analyze()
    assert len(result.components) == 1
    comp = result.components[0]
    assert comp.config_path == "db"
    assert comp.var_name == "db"
    assert comp.import_path == "myapp.db.Database"
    assert comp.kwargs == {"host": "localhost", "port": 5432}
    assert comp.is_func is False


def test_analyzer_func_entry():
    """
    GIVEN: A config with a _func entry.
    WHEN:  Analyzing the config.
    THEN:  The component is marked as a function.
    """
    config = {"joiner": {"_func": "os.path.join"}}
    result = ConfigAnalyzer(config).analyze()
    assert len(result.components) == 1
    comp = result.components[0]
    assert comp.is_func is True
    assert comp.import_path == "os.path.join"


def test_analyzer_ref_entry():
    """
    GIVEN: A config with a _ref entry.
    WHEN:  Analyzing the config.
    THEN:  A plain entry with a RefExpression is produced.
    """
    config = {
        "db": {"_type": "myapp.Database", "host": "localhost"},
        "alias": {"_ref": "db"},
    }
    result = ConfigAnalyzer(config).analyze()
    plains = [p for p in result.plains if p.config_path == "alias"]
    assert len(plains) == 1
    assert isinstance(plains[0].value, RefExpression)
    assert plains[0].value.target == "db"


def test_analyzer_ref_dotted():
    """
    GIVEN: A config with a dotted _ref path.
    WHEN:  Analyzing the config.
    THEN:  The ref target preserves the dotted path.
    """
    config = {
        "db": {"_type": "myapp.Database", "host": "localhost"},
        "pool": {"_ref": "db.pool"},
    }
    result = ConfigAnalyzer(config).analyze()
    plains = [p for p in result.plains if p.config_path == "pool"]
    assert isinstance(plains[0].value, RefExpression)
    assert plains[0].value.target == "db.pool"


def test_analyzer_deep_false():
    """
    GIVEN: A config with _deep set to false.
    WHEN:  Analyzing the config.
    THEN:  A plain entry with ellipsis value is produced.
    """
    config = {"raw": {"_deep": False, "nested": {"_type": "Foo"}}}
    result = ConfigAnalyzer(config).analyze()
    plains = [p for p in result.plains if p.config_path == "raw"]
    assert len(plains) == 1
    assert plains[0].value is ...


def test_analyzer_entries():
    """
    GIVEN: A config with an _entries mapping.
    WHEN:  Analyzing the config.
    THEN:  A plain entry with an EntriesExpression is produced.
    """
    config = {
        "mapping": {
            "_entries": [
                {"_key": "a", "_value": 1},
                {"_key": "b", "_value": 2},
            ]
        }
    }
    result = ConfigAnalyzer(config).analyze()
    plains = [p for p in result.plains if p.config_path == "mapping"]
    assert len(plains) == 1
    assert isinstance(plains[0].value, EntriesExpression)
    assert len(plains[0].value.items) == 2


def test_analyzer_plain_value():
    """
    GIVEN: A config with plain scalar values.
    WHEN:  Analyzing the config.
    THEN:  Each value produces a plain entry.
    """
    config = {"name": "hello", "count": 42}
    result = ConfigAnalyzer(config).analyze()
    assert len(result.plains) == 2


def test_analyzer_nested_type_in_kwargs():
    """
    GIVEN: A config with a nested _type inside kwargs.
    WHEN:  Analyzing the config.
    THEN:  The nested type is hoisted and replaced with a RefExpression.
    """
    config = {
        "service": {
            "_type": "myapp.Service",
            "db": {"_type": "myapp.Database", "host": "localhost"},
        }
    }
    result = ConfigAnalyzer(config).analyze()
    assert len(result.components) == 2
    service = [c for c in result.components if c.config_path == "service"][0]
    assert isinstance(service.kwargs["db"], RefExpression)


def test_analyzer_type_with_args():
    """
    GIVEN: A config with _type and _args.
    WHEN:  Analyzing the config.
    THEN:  The positional args are captured on the component.
    """
    config = {
        "point": {
            "_type": "myapp.Point",
            "_args": [1, 2, 3],
        }
    }
    result = ConfigAnalyzer(config).analyze()
    comp = result.components[0]
    assert comp.args == [1, 2, 3]


def test_analyzer_call_ignored():
    """
    GIVEN: A config with a _call directive.
    WHEN:  Analyzing the config.
    THEN:  The _call key is excluded from kwargs.
    """
    config = {
        "runner": {
            "_type": "myapp.Runner",
            "_call": {"method": "run", "args": ["x"]},
            "name": "test",
        }
    }
    result = ConfigAnalyzer(config).analyze()
    comp = result.components[0]
    assert "_call" not in comp.kwargs
    assert comp.kwargs == {"name": "test"}


def test_analyzer_instance_ignored():
    """
    GIVEN: A config with an _instance tag.
    WHEN:  Analyzing the config.
    THEN:  The _instance key is excluded from kwargs.
    """
    config = {
        "cache": {
            "_type": "myapp.Cache",
            "_instance": "shared",
            "size": 100,
        }
    }
    result = ConfigAnalyzer(config).analyze()
    comp = result.components[0]
    assert "_instance" not in comp.kwargs


def test_analyzer_topological_order_ref():
    """
    GIVEN: A config where service depends on db via _ref.
    WHEN:  Analyzing the config.
    THEN:  db appears before service in topological order.
    """
    config = {
        "service": {
            "_type": "myapp.Service",
            "db": {"_ref": "db"},
        },
        "db": {"_type": "myapp.Database", "host": "localhost"},
    }
    result = ConfigAnalyzer(config).analyze()
    db_idx = result.topological_order.index("db")
    svc_idx = result.topological_order.index("service")
    assert db_idx < svc_idx


def test_analyzer_nested_type_in_list():
    """
    GIVEN: A config with nested _type entries inside a list.
    WHEN:  Analyzing the config.
    THEN:  Nested types are hoisted and replaced with RefExpressions.
    """
    config = {
        "wrapper": {
            "_type": "myapp.Wrapper",
            "items": [
                {"_type": "myapp.Item", "name": "a"},
                {"_type": "myapp.Item", "name": "b"},
            ],
        }
    }
    result = ConfigAnalyzer(config).analyze()
    assert len(result.components) == 3
    wrapper = [c for c in result.components if c.config_path == "wrapper"][0]
    assert isinstance(wrapper.kwargs["items"], list)
    assert all(isinstance(v, RefExpression) for v in wrapper.kwargs["items"])


def test_codegen_simple_type():
    """
    GIVEN: A config with a single _type entry.
    WHEN:  Generating source code.
    THEN:  The import and typed assignment are emitted.
    """
    source = _source_for(
        {"db": {"_type": "myapp.db.Database", "host": "localhost", "port": 5432}}
    )
    assert "from myapp.db import Database" in source
    assert "db: Database = Database(host='localhost', port=5432)" in source


def test_codegen_func():
    """
    GIVEN: A config with a _func entry.
    WHEN:  Generating source code.
    THEN:  The function is imported and assigned.
    """
    source = _source_for({"joiner": {"_func": "os.path.join"}})
    assert "from os.path import join" in source
    assert "joiner = join" in source


def test_codegen_ref_simple():
    """
    GIVEN: A config with a simple _ref.
    WHEN:  Generating source code.
    THEN:  The alias is emitted as a plain assignment.
    """
    source = _source_for(
        {
            "db": {"_type": "myapp.Database", "host": "localhost"},
            "alias": {"_ref": "db"},
        }
    )
    assert "alias = db" in source


def test_codegen_ref_dotted():
    """
    GIVEN: A config with a dotted _ref path.
    WHEN:  Generating source code.
    THEN:  The dotted attribute access is emitted.
    """
    source = _source_for(
        {
            "db": {"_type": "myapp.Database", "host": "localhost"},
            "pool": {"_ref": "db.pool"},
        }
    )
    assert "pool = db.pool" in source


def test_codegen_ref_as_arg():
    """
    GIVEN: A config with a _ref used as a constructor argument.
    WHEN:  Generating source code.
    THEN:  The ref target is passed as a keyword argument.
    """
    source = _source_for(
        {
            "db": {"_type": "myapp.Database", "host": "localhost"},
            "svc": {"_type": "myapp.Service", "db": {"_ref": "db"}},
        }
    )
    assert "svc: Service = Service(db=db)" in source


def test_codegen_deep_false():
    """
    GIVEN: A config with _deep set to false.
    WHEN:  Generating source code.
    THEN:  The variable is typed as Any with ellipsis.
    """
    source = _source_for({"raw": {"_deep": False, "data": 1}})
    assert "raw: Any = ..." in source


def test_codegen_plain_values():
    """
    GIVEN: A config with plain string, int, and float values.
    WHEN:  Generating source code.
    THEN:  Each value is emitted with the correct type annotation.
    """
    source = _source_for({"name": "hello", "count": 42, "rate": 3.14})
    assert "name: str = 'hello'" in source
    assert "count: int = 42" in source
    assert "rate: float = 3.14" in source


def test_codegen_plain_bool_none():
    """
    GIVEN: A config with bool and None values.
    WHEN:  Generating source code.
    THEN:  The correct type annotations are emitted.
    """
    source = _source_for({"flag": True, "empty": None})
    assert "flag: bool = True" in source
    assert "empty: None = None" in source


def test_codegen_entries():
    """
    GIVEN: A config with an _entries mapping.
    WHEN:  Generating source code.
    THEN:  A dict literal with the entries is emitted.
    """
    source = _source_for(
        {
            "mapping": {
                "_entries": [
                    {"_key": "a", "_value": 1},
                    {"_key": "b", "_value": 2},
                ]
            }
        }
    )
    assert "mapping: dict = {" in source
    assert "'a': 1" in source
    assert "'b': 2" in source


def test_codegen_type_with_args():
    """
    GIVEN: A config with _type and _args.
    WHEN:  Generating source code.
    THEN:  Positional args appear before keyword args in the constructor call.
    """
    source = _source_for({"point": {"_type": "myapp.Point", "_args": [1, 2], "label": "p"}})
    assert "point: Point = Point(1, 2, label='p')" in source


def test_codegen_import_deduplication():
    """
    GIVEN: A config with two entries sharing the same _type.
    WHEN:  Generating source code.
    THEN:  The import statement appears only once.
    """
    source = _source_for(
        {
            "a": {"_type": "myapp.Widget", "name": "a"},
            "b": {"_type": "myapp.Widget", "name": "b"},
        }
    )
    assert source.count("from myapp import Widget") == 1


def test_codegen_nested_type_hoisted():
    """
    GIVEN: A config with a nested _type inside a constructor kwarg.
    WHEN:  Generating source code.
    THEN:  Both types are imported and each constructor call appears once.
    """
    source = _source_for(
        {
            "service": {
                "_type": "myapp.Service",
                "db": {"_type": "myapp.Database", "host": "localhost"},
            }
        }
    )
    assert "from myapp import Database" in source
    assert "from myapp import Service" in source
    lines = source.split("\n")
    db_lines = [l for l in lines if "Database(" in l]
    svc_lines = [l for l in lines if "Service(" in l]
    assert len(db_lines) == 1
    assert len(svc_lines) == 1


def test_codegen_mappings_present():
    """
    GIVEN: A config with a _type entry.
    WHEN:  Generating check source.
    THEN:  The mappings include the config path.
    """
    _, mappings = generate_check_source(
        {"db": {"_type": "myapp.Database", "host": "localhost"}}
    )
    assert len(mappings) >= 1
    assert any(m.config_path == "db" for m in mappings)


def test_codegen_config_comment_in_source():
    """
    GIVEN: A config with a _type entry.
    WHEN:  Generating source code.
    THEN:  A comment with the config path is included.
    """
    source = _source_for({"db": {"_type": "myapp.Database", "host": "localhost"}})
    assert "# config: db" in source


def test_codegen_variable_name_sanitization():
    """
    GIVEN: A config key containing a hyphen.
    WHEN:  Generating source code.
    THEN:  The variable name is sanitized to a valid identifier.
    """
    source = _source_for({"my-service": "hello"})
    assert "my_service: str = 'hello'" in source


def test_codegen_plain_dict_value():
    """
    GIVEN: A config with a plain nested dict value.
    WHEN:  Generating source code.
    THEN:  The value is emitted as a dict literal.
    """
    source = _source_for({"settings": {"timeout": 30, "retries": 3}})
    assert "settings: dict = {" in source


def test_codegen_plain_list_value():
    """
    GIVEN: A config with a plain list value.
    WHEN:  Generating source code.
    THEN:  The value is emitted as a list literal.
    """
    source = _source_for({"items": [1, 2, 3]})
    assert "items: list = [1, 2, 3]" in source
