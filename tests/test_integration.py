__author__ = "Rohan B. Dalton"

from sygaldry import Artificery, load


class Database:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port


class Service:
    def __init__(self, db: Database, url: str):
        self.db = db
        self.url = url


def test_yaml_end_to_end_includes_interpolation_refs(tmp_path, monkeypatch):
    """
    GIVEN: YAML config with includes, interpolation, and refs.
    WHEN:  Loading and resolving the config.
    THEN:  The full object graph is correctly wired.
    """
    base = tmp_path / "base.yaml"
    child = tmp_path / "child.yaml"

    base.write_text(
        "db:\n"
        '  _type: "tests.test_integration.Database"\n'
        '  host: "${DB_HOST:-localhost}"\n'
        "  port: 5432\n",
        encoding="utf-8",
    )
    child.write_text(
        "_include:\n"
        "  - base.yaml\n"
        "service:\n"
        '  _type: "tests.test_integration.Service"\n'
        '  db: { _ref: "db" }\n'
        '  url: "postgres://${db.host}:${db.port}/app"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DB_HOST", "db.local")

    resolved = load(child)

    assert resolved["service"].db is resolved["db"]
    assert resolved["service"].url == "postgres://db.local:5432/app"


def test_toml_end_to_end_includes_interpolation_refs(tmp_path):
    """
    GIVEN: TOML config with includes, interpolation, and refs.
    WHEN:  Loading and resolving the config.
    THEN:  The full object graph is correctly wired.
    """
    base = tmp_path / "base.toml"
    child = tmp_path / "child.toml"

    base.write_text(
        '[db]\n_type = "tests.test_integration.Database"\nhost = "localhost"\nport = 6000\n',
        encoding="utf-8",
    )
    child.write_text(
        '_include = ["base.toml"]\n'
        "[service]\n"
        '_type = "tests.test_integration.Service"\n'
        'url = "postgres://${db.host}:${db.port}/app"\n'
        "[service.db]\n"
        '_ref = "db"\n',
        encoding="utf-8",
    )

    resolved = Artificery(file_path=child).resolve()

    assert resolved["service"].db is resolved["db"]
    assert resolved["service"].url == "postgres://localhost:6000/app"


if __name__ == "__main__":
    pass
