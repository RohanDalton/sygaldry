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


def test_dependency_import_failure_is_preserved(mocker):
    """
    Given: A module whose dependency cannot be imported.
    When:  Resolving a dotted target in that module.
    Then:  The cause is retained and resolution never falls back to a parent.
    """
    failure = ModuleNotFoundError("dependency missing", name="private_dependency")
    imported = mocker.patch("sygaldry.types.importlib.import_module", side_effect=failure)
    with pytest.raises(ImportResolutionError) as error:
        import_dotted_path("vendor.module.Client")
    assert error.value.__cause__ is failure
    assert imported.call_count == 1


def test_module_execution_error_is_not_swallowed(mocker):
    """
    Given: A module raising a runtime error while importing.
    When:  Resolving its dotted target.
    Then:  The original error propagates without trying unrelated parent imports.
    """
    failure = RuntimeError("module execution failed")
    imported = mocker.patch("sygaldry.types.importlib.import_module", side_effect=failure)
    with pytest.raises(RuntimeError) as error:
        import_dotted_path("vendor.module.Client")
    assert error.value is failure
    assert imported.call_count == 1


if __name__ == "__main__":
    pass
