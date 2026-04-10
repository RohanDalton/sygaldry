__author__ = "Rohan B. Dalton"

import http.server
import threading
from urllib.error import URLError

import pytest

from sygaldry.errors import (
    CircularIncludeError,
    CircularInterpolationError,
    InterpolationError,
    ParseError,
)
from sygaldry.loader import load_config


def test_load_config_yaml_with_include_and_merge(tmp_path):
    """
    GIVEN: A YAML file that includes another.
    WHEN:  Loading the config.
    THEN:  Deep-merge applies and includes are loaded first.
    """
    base = tmp_path / "base.yaml"
    child = tmp_path / "child.yaml"

    base.write_text(
        "service:\n  host: localhost\n  port: 5432\n",
        encoding="utf-8",
    )
    child.write_text(
        "_include:\n  - base.yaml\nservice:\n  port: 6543\n",
        encoding="utf-8",
    )

    config = load_config(child)

    assert config["service"]["host"] == "localhost"
    assert config["service"]["port"] == 6543


def test_load_config_toml_with_include_and_merge(tmp_path):
    """
    GIVEN: A TOML file that includes another.
    WHEN:  Loading the config.
    THEN:  Deep-merge applies and includes are loaded first.
    """
    base = tmp_path / "base.toml"
    child = tmp_path / "child.toml"

    base.write_text(
        '[service]\nname = "core"\nport = 9000\n',
        encoding="utf-8",
    )
    child.write_text(
        '_include = ["base.toml"]\n[service]\nport = 9001\n',
        encoding="utf-8",
    )

    config = load_config(child)

    assert config["service"]["name"] == "core"
    assert config["service"]["port"] == 9001


def test_interpolation_env_and_config_paths(tmp_path, monkeypatch):
    """
    GIVEN: A config with env var and config path interpolation.
    WHEN:  Loading the config with DB_HOST set in the environment.
    THEN:  Env vars resolve for keys not in config and config paths resolve.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        'db:\n  host: localhost\n  port: "${DB_PORT:-5432}"\n'
        'url: "postgres://${DB_HOST:-${db.host}}:${db.port}/app"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DB_HOST", "db.example.com")

    config = load_config(cfg)

    assert config["db"]["port"] == 5432
    assert config["url"] == "postgres://db.example.com:5432/app"


def test_interpolation_escape(tmp_path):
    """
    GIVEN: A config with escaped interpolation placeholders.
    WHEN:  Loading the config.
    THEN:  Escaped placeholders are preserved as literals.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('value: "$${NOT_INTERP}"\n', encoding="utf-8")

    config = load_config(cfg)

    assert config["value"] == "${NOT_INTERP}"


def test_interpolation_nested_default(tmp_path):
    """
    GIVEN: A config with nested interpolation defaults.
    WHEN:  Loading the config.
    THEN:  Nested tokens in the default are resolved.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('db:\n  host: localhost\nurl: "${DB_HOST:-${db.host}}"\n', encoding="utf-8")

    config = load_config(cfg)

    assert config["url"] == "localhost"


def test_interpolation_nested_tokens_inside_string(tmp_path, monkeypatch):
    """
    GIVEN: A string with multiple nested interpolation tokens.
    WHEN:  Loading the config with DB_HOST set in the environment.
    THEN:  All tokens are resolved and combined correctly.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "db:\n  host: localhost\n  port: 5432\n"
        'url: "postgres://${DB_HOST:-${db.host}}:${db.port}/app"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("DB_HOST", "db.example.com")

    config = load_config(cfg)

    assert config["url"] == "postgres://db.example.com:5432/app"


def test_interpolation_missing_target_raises(tmp_path):
    """
    GIVEN: A config referencing a missing interpolation target.
    WHEN:  Loading the config.
    THEN:  An InterpolationError is raised.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('value: "${missing.path}"\n', encoding="utf-8")

    with pytest.raises(InterpolationError):
        load_config(cfg)


def test_circular_interpolation_detection(tmp_path):
    """
    GIVEN: A config with circular interpolation references.
    WHEN:  Loading the config.
    THEN:  A CircularInterpolationError is raised.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('a: "${b}"\nb: "${a}"\n', encoding="utf-8")

    with pytest.raises(CircularInterpolationError):
        load_config(cfg)


def test_diamond_include_does_not_raise(tmp_path):
    """
    GIVEN: A includes [B, C] and both B and C include D (diamond).
    WHEN:  Loading the config.
    THEN:  The diamond dependency resolves without error and D is loaded once.
    """
    d = tmp_path / "d.yaml"
    b = tmp_path / "b.yaml"
    c = tmp_path / "c.yaml"
    a = tmp_path / "a.yaml"

    d.write_text("shared:\n  value: 42\n", encoding="utf-8")
    b.write_text("_include:\n  - d.yaml\nb_key: from_b\n", encoding="utf-8")
    c.write_text("_include:\n  - d.yaml\nc_key: from_c\n", encoding="utf-8")
    a.write_text("_include:\n  - b.yaml\n  - c.yaml\na_key: from_a\n", encoding="utf-8")

    config = load_config(a)

    assert config["shared"]["value"] == 42
    assert config["b_key"] == "from_b"
    assert config["c_key"] == "from_c"
    assert config["a_key"] == "from_a"


def test_interpolation_config_path_takes_priority_over_env(tmp_path, monkeypatch):
    """
    GIVEN: A config key that matches an environment variable name.
    WHEN:  Interpolating that key.
    THEN:  The config value is used, not the env var.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('host: config_host\nurl: "${host}"\n', encoding="utf-8")
    monkeypatch.setenv("host", "env_host")

    config = load_config(cfg)

    assert config["url"] == "config_host"


def test_interpolation_falls_back_to_env_when_not_in_config(tmp_path, monkeypatch):
    """
    GIVEN: An interpolation key not present in config but set in the environment.
    WHEN:  Interpolating that key.
    THEN:  The environment variable value is used.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text('url: "${SYGALDRY_TEST_VAR}"\n', encoding="utf-8")
    monkeypatch.setenv("SYGALDRY_TEST_VAR", "from_env")

    config = load_config(cfg)

    assert config["url"] == "from_env"


def test_dotted_keys_expand_to_nested_dicts(tmp_path):
    """
    GIVEN: A config with dotted top-level keys.
    WHEN:  Loading the config.
    THEN:  Dotted keys are expanded into nested dicts.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "ftp_client:\n  host: null\n  port: 22\n"
        "ftp_client.host: foo.com\n"
        "ftp_client.port: 2222\n",
        encoding="utf-8",
    )

    config = load_config(cfg)

    assert config["ftp_client"]["host"] == "foo.com"
    assert config["ftp_client"]["port"] == 2222


def test_dotted_keys_with_include(tmp_path):
    """
    GIVEN: A config that includes another and overrides via dotted keys.
    WHEN:  Loading the config.
    THEN:  Dotted keys override the included values.
    """
    base = tmp_path / "sftp.yaml"
    base.write_text(
        "ftp_client:\n  host: null\n  port: 22\n  timeout: 3600\n",
        encoding="utf-8",
    )
    child = tmp_path / "vendor.yaml"
    child.write_text(
        "_include:\n  - sftp.yaml\nftp_client.host: foo.com\nftp_client.timeout: 100\n",
        encoding="utf-8",
    )

    config = load_config(child)

    assert config["ftp_client"]["host"] == "foo.com"
    assert config["ftp_client"]["port"] == 22
    assert config["ftp_client"]["timeout"] == 100


def test_circular_include_detection(tmp_path):
    """
    GIVEN: Two config files that include each other.
    WHEN:  Loading the config.
    THEN:  A CircularIncludeError is raised.
    """
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"

    a.write_text("_include:\n  - b.yaml\nvalue: 1\n", encoding="utf-8")
    b.write_text("_include:\n  - a.yaml\nvalue: 2\n", encoding="utf-8")

    with pytest.raises(CircularIncludeError):
        load_config(a)


@pytest.fixture()
def _serve_dir(tmp_path):
    """Serve *tmp_path* over HTTP on a random port and yield the base URL."""
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(
        *a, directory=str(tmp_path), **kw
    )
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


def test_load_config_from_http_url(tmp_path, _serve_dir):
    """
    GIVEN: A YAML config served over HTTP.
    WHEN:  load_config is called with the URL.
    THEN:  The config is loaded correctly.
    """
    (tmp_path / "remote.yaml").write_text(
        "service:\n  host: remote-host\n  port: 9090\n", encoding="utf-8"
    )
    config = load_config(f"{_serve_dir}/remote.yaml")
    assert config["service"]["host"] == "remote-host"
    assert config["service"]["port"] == 9090


def test_load_config_from_http_url_toml(tmp_path, _serve_dir):
    """
    GIVEN: A TOML config served over HTTP.
    WHEN:  load_config is called with the URL.
    THEN:  The config is loaded correctly.
    """
    (tmp_path / "remote.toml").write_text(
        '[service]\nhost = "toml-host"\nport = 8080\n', encoding="utf-8"
    )
    config = load_config(f"{_serve_dir}/remote.toml")
    assert config["service"]["host"] == "toml-host"
    assert config["service"]["port"] == 8080


def test_http_config_with_absolute_url_include(tmp_path, _serve_dir):
    """
    GIVEN: A remote YAML config that includes another remote file via absolute URL.
    WHEN:  load_config is called with the URL.
    THEN:  Both files are merged correctly.
    """
    (tmp_path / "base.yaml").write_text(
        "db:\n  host: db-host\n  port: 5432\n", encoding="utf-8"
    )
    (tmp_path / "app.yaml").write_text(
        f'_include:\n  - "{_serve_dir}/base.yaml"\ndb:\n  port: 6543\n',
        encoding="utf-8",
    )
    config = load_config(f"{_serve_dir}/app.yaml")
    assert config["db"]["host"] == "db-host"
    assert config["db"]["port"] == 6543


def test_http_config_download_failure_raises():
    """
    GIVEN: A URL that cannot be reached.
    WHEN:  load_config is called.
    THEN:  A ParseError is raised.
    """
    with pytest.raises(URLError, match="Connection refused"):
        load_config("http://127.0.0.1:1/nonexistent.yaml")


def test_http_config_with_interpolation(tmp_path, _serve_dir):
    """
    GIVEN: A remote config with interpolation.
    WHEN:  load_config is called.
    THEN:  Interpolation resolves correctly.
    """
    (tmp_path / "interp.yaml").write_text(
        'db:\n  host: myhost\n  port: 5432\nurl: "postgres://${db.host}:${db.port}/app"\n',
        encoding="utf-8",
    )
    config = load_config(f"{_serve_dir}/interp.yaml")
    assert config["url"] == "postgres://myhost:5432/app"


if __name__ == "__main__":
    pass
