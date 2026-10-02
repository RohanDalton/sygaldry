__author__ = "Rohan B. Dalton"

import pytest

from sygaldry import Artificery, load
from sygaldry.cache import Instances

_CONFIG_CONTENT_CASES = {"empty": "", "populated": "host: original\n"}


class Widget:
    def __init__(self, name: str, weight: int = 0):
        self.name = name
        self.weight = weight


class Assembly:
    def __init__(self, widget: Widget):
        self.widget = widget


def test_artificery_raises_without_config_or_path():
    """
    GIVEN: Neither paths nor config provided.
    WHEN:  Constructing an Artificery instance.
    THEN:  A ValueError is raised.
    """
    with pytest.raises(ValueError, match="requires at least one path or a config dict"):
        Artificery()


def test_artificery_accepts_config_dict():
    """
    GIVEN: A pre-loaded config dict with a _type entry.
    WHEN:  Constructing and resolving via Artificery.
    THEN:  The object graph is built from the dict.
    """
    config = {
        "w": {"_type": "tests.test_artificery.Widget", "name": "bolt", "weight": 5},
    }

    resolved = Artificery(config=config).resolve()

    assert resolved["w"].name == "bolt"
    assert resolved["w"].weight == 5


def test_artificery_accepts_file_path(tmp_path):
    """
    GIVEN: A YAML config file with a _type entry.
    WHEN:  Constructing Artificery with file_path and resolving.
    THEN:  The object graph is built from the file.
    """
    cfg = tmp_path / "widgets.yaml"
    cfg.write_text(
        'w:\n  _type: "tests.test_artificery.Widget"\n  name: gear\n',
        encoding="utf-8",
    )

    resolved = Artificery(cfg).resolve()

    assert resolved["w"].name == "gear"


def test_artificery_accepts_string_path(tmp_path):
    """
    GIVEN: A config file path passed as a string.
    WHEN:  Constructing Artificery with a str file_path and resolving.
    THEN:  The path is converted to Path and the config resolves.
    """
    cfg = tmp_path / "widgets.yaml"
    cfg.write_text(
        'w:\n  _type: "tests.test_artificery.Widget"\n  name: cog\n',
        encoding="utf-8",
    )

    resolved = Artificery(str(cfg)).resolve()

    assert resolved["w"].name == "cog"


def test_artificery_shared_cache_reuses_instances():
    """
    GIVEN: Two Artificery instances sharing the same cache.
    WHEN:  Both resolve a _type with the same spec.
    THEN:  The same object instance is returned.
    """
    shared_cache = Instances()
    config = {
        "w": {
            "_type": "tests.test_artificery.Widget",
            "_instance": "shared",
            "name": "rivet",
        },
    }

    first = Artificery(config=config, cache=shared_cache).resolve()
    second = Artificery(config=config, cache=shared_cache).resolve()

    assert first["w"] is second["w"]


def test_artificery_transient_skips_cache():
    """
    GIVEN: Artificery in transient mode.
    WHEN:  Resolving the same config twice with the same cache.
    THEN:  Different object instances are created each time.
    """
    shared_cache = Instances()
    config = {
        "w": {
            "_type": "tests.test_artificery.Widget",
            "_instance": "shared",
            "name": "pin",
        },
    }

    first = Artificery(config=config, cache=shared_cache, transient=True).resolve()
    second = Artificery(config=config, cache=shared_cache, transient=True).resolve()

    assert first["w"] is not second["w"]
    assert first["w"].name == second["w"].name


def test_artificery_resolves_refs_between_entries():
    """
    GIVEN: A config where one entry references another via _ref.
    WHEN:  Resolving via Artificery.
    THEN:  The reference points to the same resolved object.
    """
    config = {
        "w": {"_type": "tests.test_artificery.Widget", "name": "spring"},
        "a": {"_type": "tests.test_artificery.Assembly", "widget": {"_ref": "w"}},
    }

    resolved = Artificery(config=config).resolve()

    assert resolved["a"].widget is resolved["w"]


def test_artificery_config_loads_mapping(tmp_path):
    """
    GIVEN: A YAML config file.
    WHEN:  Accessing Artificery.config.
    THEN:  The parsed and interpolated mapping is returned.
    """
    cfg = tmp_path / "config.yaml"
    cfg.write_text("service:\n  host: localhost\n  port: 8080\n", encoding="utf-8")

    config = Artificery(cfg).config

    assert config["service"]["host"] == "localhost"
    assert config["service"]["port"] == 8080


def test_artificery_config_interpolates_without_instantiating_components(tmp_path):
    """
    GIVEN: A YAML config file with interpolation.
    WHEN:  Accessing Artificery.config.
    THEN:  Interpolation is applied but _type entries are not resolved.
    """
    cfg = tmp_path / "raw.yaml"
    cfg.write_text(
        "host: localhost\nurl: 'http://${host}:8080'\n"
        "svc:\n  _type: 'tests.test_artificery.Widget'\n  name: raw\n",
        encoding="utf-8",
    )

    config = Artificery(cfg).config

    assert config["url"] == "http://localhost:8080"
    assert config["svc"]["_type"] == "tests.test_artificery.Widget"


def test_artificery_config_prepares_merged_files_before_resolution(tmp_path):
    """
    Given: Multiple files with includes, component specs, and interpolation.
    When:  Accessing config with use mappings and overrides.
    Then:  Files merge before uses, overrides, and interpolation are applied.
    """
    included_path = tmp_path / "included.yaml"
    base_path = tmp_path / "base.yaml"
    override_path = tmp_path / "override.yaml"
    included_path.write_text("service:\n  timeout: 30\n", encoding="utf-8")
    base_path.write_text(
        "_include:\n  - included.yaml\n"
        "service:\n  host: base\n  port: 8080\n"
        "widget:\n  _type: tests.test_artificery.Widget\n  name: '${service.host}'\n"
        "endpoint: '${service.host}:${service.port}'\n"
        "copied_host: '${selected_host}'\n",
        encoding="utf-8",
    )
    override_path.write_text("service:\n  host: production\n", encoding="utf-8")
    expected = {
        "service": {"timeout": 30, "host": "cli", "port": 8080},
        "widget": {"_type": "tests.test_artificery.Widget", "name": "cli"},
        "endpoint": "cli:8080",
        "copied_host": "production",
        "selected_host": "production",
    }

    actual = Artificery(
        base_path,
        override_path,
        uses={"selected_host": "service.host"},
        overrides={"service.host": "cli"},
    ).config

    assert actual == expected


@pytest.mark.parametrize(
    "config_content", _CONFIG_CONTENT_CASES.values(), ids=_CONFIG_CONTENT_CASES
)
def test_artificery_config_caches_prepared_mapping(tmp_path, config_content):
    """
    Given: A config file that has already been prepared, including an empty file.
    When:  The source changes and config is accessed again.
    Then:  The original prepared mapping is reused.
    """
    config_path = tmp_path / "cached.yaml"
    config_path.write_text(config_content, encoding="utf-8")
    artificery = Artificery(config_path)
    expected = artificery.config
    config_path.write_text("host: changed\n", encoding="utf-8")

    actual = artificery.config

    assert actual is expected


def test_load_resolves_end_to_end(tmp_path):
    """
    GIVEN: A YAML config file with types and refs.
    WHEN:  Using the top-level load() function.
    THEN:  The full object graph is resolved.
    """
    cfg = tmp_path / "full.yaml"
    cfg.write_text(
        "w:\n  _type: 'tests.test_artificery.Widget'\n  name: washer\n"
        "a:\n  _type: 'tests.test_artificery.Assembly'\n"
        "  widget: { _ref: 'w' }\n",
        encoding="utf-8",
    )

    resolved = load(cfg)

    assert resolved["a"].widget is resolved["w"]
    assert resolved["w"].name == "washer"


if __name__ == "__main__":
    pass
