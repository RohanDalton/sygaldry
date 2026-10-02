__author__ = "Rohan B. Dalton"

import stat
import subprocess
from pathlib import Path

import pytest

from sygaldry import Artificery, Secret
from sygaldry.checker import check
from sygaldry.cli import _parse_set_option, cli
from sygaldry.codegen import generate_check_source
from sygaldry.errors import InterpolationError
from sygaldry.secrets import redact


def test_cli_preserves_zero_prefixed_identifiers(identifier):
    """
    Given: A zero-prefixed identifier supplied as a CLI override.
    When:  Parsing the value.
    Then:  The identifier remains a string with all digits intact.
    """
    expected = ("identifier", identifier["value"])
    actual = _parse_set_option(f"identifier={identifier['value']}")
    assert actual == expected


def test_yaml_preserves_zero_prefixed_identifiers(tmp_path, identifier):
    """
    Given: An unquoted zero-prefixed identifier in YAML.
    When:  Loading the file and resolving a copy through interpolation.
    Then:  YAML parsing and interpolation both preserve the identifier.
    """
    path = tmp_path / "identifier.yaml"
    path.write_text(
        f"identifier: {identifier['value']}\ncopy: '${{identifier}}'\n", encoding="utf-8"
    )
    expected = {"identifier": identifier["value"], "copy": identifier["value"]}
    actual = Artificery(path).resolve()
    assert actual == expected


def test_interpolation_preserves_quoted_numeric_config_strings():
    """
    Given: A string containing canonical digits in an in-memory config.
    When:  Referencing it with a whole-value placeholder.
    Then:  The existing string type is retained.
    """
    expected = {"identifier": "123", "copy": "123"}
    actual = Artificery(config={"identifier": "123", "copy": "${identifier}"}).resolve()
    assert actual == expected


def test_environment_identifier_preserves_digits(mocker, identifier):
    """
    Given: An identifier obtained from the environment.
    When:  Interpolating and resolving it.
    Then:  Its protected representation still delivers the complete string.
    """
    mocker.patch.dict("os.environ", {"IDENTIFIER": identifier["value"]})
    runtime = Artificery(config={"identifier": "${IDENTIFIER}"})
    assert isinstance(runtime.config["identifier"], Secret)
    assert runtime.resolve("identifier") == identifier["value"]


def test_secret_values_are_unwrapped_at_constructor_boundary():
    """
    Given: A constructor argument explicitly marked secret.
    When:  Constructing the component.
    Then:  The constructor receives the real value while config remains protected.
    """
    runtime = Artificery(
        config={
            "resource": {
                "_type": "tests.components.Plain",
                "name": {"_secret": "private-name"},
            }
        }
    )
    actual = runtime.resolve("resource")
    assert actual.name == "private-name"
    assert "private-name" not in repr(runtime.config)


def test_environment_taint_propagates_through_interpolation(mocker):
    """
    Given: A secret environment value under a neutral config name.
    When:  Building a connection string and a second config reference.
    Then:  All derived strings stay protected in config displays and generated source.
    """
    mocker.patch.dict("os.environ", {"PRIVATE_VALUE": "dont-print-this"})
    runtime = Artificery(
        config={
            "neutral": "${PRIVATE_VALUE}",
            "connection": "prefix/${neutral}",
            "copy": "${connection}",
        }
    )
    source, _ = generate_check_source(runtime.config)
    assert "dont-print-this" not in repr(redact(runtime.config))
    assert "dont-print-this" not in source
    assert runtime.resolve("copy") == "prefix/dont-print-this"


def test_secret_mapping_keys_are_rejected(mocker):
    """
    Given: A protected environment value used as a mapping key.
    When:  Preparing the configuration.
    Then:  A safe diagnostic prevents leaking the secret in paths and keys.
    """
    mocker.patch.dict("os.environ", {"PRIVATE_VALUE": "dont-print-this"})
    with pytest.raises(InterpolationError) as error:
        _ = Artificery(config={"${PRIVATE_VALUE}": "value"}).config
    assert "dont-print-this" not in str(error.value)


def test_cli_displays_hide_secret_values(tmp_path, cli_runner, display_arguments, mocker):
    """
    Given: Named, explicitly marked, and environment-derived secrets.
    When:  Displaying the prepared or resolved config or a dry run.
    Then:  Secret values never appear in output.
    """
    mocker.patch.dict("os.environ", {"PRIVATE_VALUE": "environment-secret"})
    path = tmp_path / "secret.yaml"
    path.write_text(
        "password: named-secret\n"
        "neutral: '${PRIVATE_VALUE}'\n"
        "resource:\n  _type: tests.components.Plain\n  name:\n    _secret: explicit-secret\n",
        encoding="utf-8",
    )
    actual = cli_runner.invoke(cli, [*display_arguments, "-c", str(path)])
    assert actual.exit_code == 0, actual.output
    for secret in ("named-secret", "environment-secret", "explicit-secret"):
        assert secret not in actual.output


def test_check_source_never_contains_secrets_and_is_removed(tmp_path, mocker):
    """
    Given: A config containing a secret constructor argument.
    When:  Running a type checker.
    Then:  Its private temporary source uses safe placeholders and is removed.
    """
    captured_paths = list()

    def invoke(checker, filepath):
        path = Path(filepath)
        captured_paths.append(path)
        assert "private-name" not in path.read_text()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        result = subprocess.CompletedProcess([checker], 0, stdout="", stderr="")
        return result

    mocker.patch("sygaldry.checker._invoke_checker", side_effect=invoke)
    expected = list()
    actual = check(
        config={
            "resource": {"_type": "tests.components.Plain", "name": Secret("private-name")}
        },
        type_checker="ty",
    )
    assert actual == expected
    assert len(captured_paths) == 1
    assert not captured_paths[0].exists()
    assert not captured_paths[0].parent.exists()


def test_check_removes_source_after_checker_failure(mocker):
    """
    Given: A checker that times out after receiving its temporary source.
    When:  Checking the config.
    Then:  The temporary source and directory are removed even on failure.
    """
    captured_paths = list()

    def invoke(checker, filepath):
        captured_paths.append(Path(filepath))
        raise subprocess.TimeoutExpired(checker, 1)

    mocker.patch("sygaldry.checker._invoke_checker", side_effect=invoke)
    with pytest.raises(subprocess.TimeoutExpired):
        check(config={"value": 1}, type_checker="ty")
    assert not captured_paths[0].exists()
    assert not captured_paths[0].parent.exists()


if __name__ == "__main__":
    pass
