__author__ = "Rohan B. Dalton"

import pytest

from sygaldry import Artificery, load
from sygaldry.artificery import ArtificeryLoader, load_config_file
from sygaldry.cache import Instances


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


def test_artificery_loader_loads_config(tmp_path):
    """
    GIVEN: A YAML config file.
    WHEN:  Loading via ArtificeryLoader.
    THEN:  The parsed and interpolated mapping is returned.
    """
    cfg = tmp_path / "loader.yaml"
    cfg.write_text("service:\n  host: localhost\n  port: 8080\n", encoding="utf-8")

    loader = ArtificeryLoader(cfg)
    config = loader.load()

    assert config["service"]["host"] == "localhost"
    assert config["service"]["port"] == 8080


def test_load_config_file_returns_interpolated_mapping(tmp_path):
    """
    GIVEN: A YAML config file with interpolation.
    WHEN:  Loading via load_config_file.
    THEN:  Interpolation is applied but _type entries are not resolved.
    """
    cfg = tmp_path / "raw.yaml"
    cfg.write_text(
        "host: localhost\nurl: 'http://${host}:8080'\n"
        "svc:\n  _type: 'tests.test_artificery.Widget'\n  name: raw\n",
        encoding="utf-8",
    )

    config = load_config_file(cfg)

    assert config["url"] == "http://localhost:8080"
    assert config["svc"]["_type"] == "tests.test_artificery.Widget"


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
