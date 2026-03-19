__author__ = "Rohan B. Dalton"

from pathlib import Path

from sygaldry import Artificery


class Leaf:
    def __init__(self, value: int) -> None:
        self.value = value


class Branch:
    def __init__(self, labels: dict[str, int], leaves: dict[str, Leaf]) -> None:
        self.labels = labels
        self.leaves = leaves


class Root:
    def __init__(self, primary: Branch) -> None:
        self.primary = primary


def test_yaml_deep_objects_with_key_refs():
    """
    GIVEN: A YAML config with deep objects and _entries key refs.
    WHEN:  Resolving the config.
    THEN:  Keys and values resolve correctly with caching.
    """
    config_path = Path(__file__).parent / "fixtures" / "deep_key_refs.yaml"

    resolved = Artificery(file_path=config_path).resolve()

    root = resolved["root"]
    branch = resolved["branch"]
    assert root.primary is branch
    assert branch.labels["alpha"] == 1
    assert branch.labels["beta"] == 2
    assert branch.leaves["alpha"] is resolved["leaf_a"]
    assert branch.leaves["beta"] is resolved["leaf_b"]
    assert branch.leaves["alpha"].value == 1
    assert branch.leaves["beta"].value == 2


def test_toml_deep_objects_with_key_refs():
    """
    GIVEN: A TOML config with deep objects and _entries key refs.
    WHEN:  Resolving the config.
    THEN:  Keys and values resolve correctly with caching.
    """
    config_path = Path(__file__).parent / "fixtures" / "deep_key_refs.toml"

    resolved = Artificery(file_path=config_path).resolve()

    root = resolved["root"]
    branch = resolved["branch"]
    assert root.primary is branch
    assert branch.labels["alpha"] == 1
    assert branch.labels["beta"] == 2
    assert branch.leaves["alpha"] is resolved["leaf_a"]
    assert branch.leaves["beta"] is resolved["leaf_b"]
    assert branch.leaves["alpha"].value == 1
    assert branch.leaves["beta"].value == 2


if __name__ == "__main__":
    pass
