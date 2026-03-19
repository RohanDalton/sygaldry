__author__ = "Rohan B. Dalton"

import pytest

from sygaldry.errors import ImportResolutionError
from sygaldry.types import import_dotted_path


def test_import_dotted_path_resolves_attribute():
    """
    GIVEN: A dotted path to a callable in the standard library.
    WHEN:  Importing the path.
    THEN:  A callable is returned.
    """
    target = import_dotted_path("os.path.join")

    assert callable(target)


def test_import_dotted_path_rejects_empty_string():
    """
    GIVEN: An empty string as the dotted path.
    WHEN:  Importing the path.
    THEN:  An ImportResolutionError is raised.
    """
    with pytest.raises(ImportResolutionError, match="non-empty string"):
        import_dotted_path("")


if __name__ == "__main__":
    pass
