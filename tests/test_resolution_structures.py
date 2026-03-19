__author__ = "Rohan B. Dalton"

from sygaldry.resolver import resolve_config


class Wrapper:
    def __init__(self, values):
        self.values = values


class Holder:
    def __init__(self, items):
        self.items = items


def test_nested_constructor_specs_in_lists_and_dicts():
    """
    GIVEN: Nested constructor specs inside lists and dicts.
    WHEN:  Resolving the configuration.
    THEN:  Config is resolved bottom-up.
    """
    config = {
        "wrapped": {
            "_type": "tests.test_resolution_structures.Wrapper",
            "values": [
                {"_type": "tests.test_resolution_structures.Holder", "items": {"a": 1}},
                {"_type": "tests.test_resolution_structures.Holder", "items": {"b": 2}},
            ],
        }
    }

    resolved = resolve_config(config)

    assert resolved["wrapped"].values[0].items["a"] == 1
    assert resolved["wrapped"].values[1].items["b"] == 2


if __name__ == "__main__":
    pass
