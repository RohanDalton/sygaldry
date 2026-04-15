from __future__ import annotations

import pytest
from click.testing import CliRunner

from sygaldry.cli import cli


class Greeter:
    def __init__(self, name: str):
        self.name = name

    def __call__(self, *args):
        return f"Hello, {self.name}!"

    def greet(self, greeting: str = "Hi"):
        return f"{greeting}, {self.name}!"

    def add(self, a, b):
        return a + b


class Pipeline:
    def __init__(self, batch_size: int = 100):
        self.batch_size = batch_size

    def execute(self, mode: str = "default"):
        return f"executed:{mode}:{self.batch_size}"

    def __call__(self):
        return f"pipeline:{self.batch_size}"


class AsyncGreeter:
    def __init__(self, name: str):
        self.name = name

    async def __call__(self, *args):
        return f"Hello async, {self.name}!"

    async def greet(self, greeting: str = "Hi"):
        return f"{greeting} async, {self.name}!"


class ExitCodeRunner:
    def run(self):
        return 0

    def fail(self):
        return 1


@pytest.fixture()
def runner():
    return CliRunner()


def _write_cfg(tmp_path, name, content):
    cfg = tmp_path / name
    cfg.write_text(content, encoding="utf-8")
    return str(cfg)


def test_run_basic_callable(tmp_path, runner):
    """
    GIVEN: A config with a callable object
    WHEN:  We use run
    THEN:  __call__ is invoked.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: world\n",
    )
    result = runner.invoke(cli, ["run", "-c", cfg, "greeter"])
    assert result.exit_code == 0
    assert "Hello, world!" in result.output


def test_run_deep_merge(tmp_path, runner):
    """
    GIVEN: Two config files
    WHEN:  We use `run`
    THEN:  They are deep-merged.
    """
    base = _write_cfg(
        tmp_path,
        "base.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: base\n",
    )
    override = _write_cfg(
        tmp_path,
        "override.yaml",
        "greeter:\n  name: override\n",
    )
    result = runner.invoke(cli, ["run", "-c", base, "-c", override, "greeter"])
    assert result.exit_code == 0
    assert "Hello, override!" in result.output


def test_run_set_override(tmp_path, runner):
    """
    GIVEN: A config
    WHEN:  --set overrides a value
    THEN:  The override value is used.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: original\n",
    )
    result = runner.invoke(
        cli,
        ["run", "-c", cfg, "greeter", "--set", "greeter.name=overridden"],
    )
    assert result.exit_code == 0
    assert "Hello, overridden!" in result.output


def test_run_use_substitution(tmp_path, runner):
    """
    GIVEN: A config with defaults
    WHEN:  --use copies a value
    THEN:  The target is updated.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "defaults:\n"
        "  formal_name: Dr. Smith\n"
        "greeter:\n"
        "  _type: tests.test_cli_integration.Greeter\n"
        "  name: casual\n",
    )
    result = runner.invoke(
        cli,
        [
            "run",
            "-c",
            cfg,
            "greeter",
            "--use",
            "greeter.name=defaults.formal_name",
        ],
    )
    assert result.exit_code == 0
    assert "Hello, Dr. Smith!" in result.output


def test_run_method_selection(tmp_path, runner):
    """
    GIVEN: A valid config
    WHEN: --method is specified
    THEN: That method is called.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: Alice\n",
    )
    result = runner.invoke(
        cli,
        ["run", "-c", cfg, "greeter", "--method", "greet"],
    )
    assert result.exit_code == 0
    assert "Hi, Alice!" in result.output


def test_run_method_with_args(tmp_path, runner):
    """
    GIVEN: A valid config
    WHEN:  Method args are passed after --
    THEN:  They are forwarded.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: Alice\n",
    )
    result = runner.invoke(
        cli,
        [
            "run",
            "-c",
            cfg,
            "greeter",
            "--method",
            "greet",
            "--",
            "Hey",
        ],
    )
    assert result.exit_code == 0
    assert "Hey, Alice!" in result.output


def test_run_call_defaults(tmp_path, runner):
    """
    GIVEN: A config with _call
    WHEN:  We use run without --method
    THEN:  _call defaults are used.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "pipeline:\n"
        "  _type: tests.test_cli_integration.Pipeline\n"
        "  batch_size: 500\n"
        "  _call:\n"
        "    method: execute\n"
        "    args:\n"
        "      - weekly\n",
    )
    result = runner.invoke(cli, ["run", "-c", cfg, "pipeline"])
    assert result.exit_code == 0
    assert "executed:weekly:500" in result.output


def test_run_cli_overrides_call_defaults(tmp_path, runner):
    """
    GIVEN: A config with _call
    WHEN:  --method is specified
    THEN:  The value from the CLI wins.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "pipeline:\n"
        "  _type: tests.test_cli_integration.Pipeline\n"
        "  _call:\n"
        "    method: execute\n"
        "    args:\n"
        "      - weekly\n",
    )
    result = runner.invoke(
        cli,
        ["run", "-c", cfg, "pipeline", "--", "daily"],
    )
    assert result.exit_code == 0
    assert "executed:daily:100" in result.output


def test_run_dry_run(tmp_path, runner):
    """
    GIVEN: A --dry-run flag
    WHEN:  We use run
    THEN:  The config is validated but nothing is called.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: world\n",
    )
    result = runner.invoke(cli, ["run", "-c", cfg, "greeter", "--dry-run"])
    assert result.exit_code == 0
    assert "Hello, world!" not in result.output
    assert "Dry run summary" in result.output


def test_run_int_return_becomes_exit_code(tmp_path, runner):
    """
    GIVEN: A method returning int
    WHEN:  We use run
    THEN:  The exit code matches the return value.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "runner:\n  _type: tests.test_cli_integration.ExitCodeRunner\n",
    )
    result = runner.invoke(cli, ["run", "-c", cfg, "runner", "--method", "run"])
    assert result.exit_code == 0

    result = runner.invoke(cli, ["run", "-c", cfg, "runner", "--method", "fail"])
    assert result.exit_code == 1


def test_run_quiet_suppresses_output(tmp_path, runner):
    """
    GIVEN: A --quiet flag
    WHEN:  We use run
    THEN:  Any non-error output is suppressed.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: world\n",
    )
    result = runner.invoke(cli, ["run", "-c", cfg, "greeter", "-q"])
    assert result.exit_code == 0
    assert "Hello, world!" not in result.output


def test_show_merged_config(tmp_path, runner):
    """
    GIVEN: Any config
    WHEN:  We use show
    THEN:  The merged config is displayed.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "db:\n  host: localhost\n  port: 5432\n",
    )
    result = runner.invoke(cli, ["show", "-c", cfg])
    assert result.exit_code == 0
    assert "localhost" in result.output


def test_show_python_output(tmp_path, runner):
    """
    GIVEN: A config with a typed component
    WHEN:  We use show (default mode)
    THEN:  Generated Python code is displayed.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: world\n",
    )
    result = runner.invoke(cli, ["show", "-c", cfg])
    assert result.exit_code == 0
    assert "from tests.test_cli_integration import Greeter" in result.output
    assert "Greeter(name='world')" in result.output


def test_show_single_object(tmp_path, runner):
    """
    GIVEN: Any config
    WHEN:  We call using show --object
    THEN:  Only that key is shown.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "db:\n  host: localhost\nservice:\n  name: web\n",
    )
    result = runner.invoke(cli, ["show", "-c", cfg, "--raw", "--object", "db"])
    assert result.exit_code == 0
    assert "localhost" in result.output
    assert "web" not in result.output


def test_show_json_format(tmp_path, runner):
    """
    GIVEN: Any config
    WHEN:  We call using show --format json
    THEN  The output is json
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "db:\n  host: localhost\n",
    )
    result = runner.invoke(cli, ["show", "-c", cfg, "--raw", "--format", "json"])
    assert result.exit_code == 0
    assert '"host"' in result.output
    assert '"localhost"' in result.output


def test_show_list_objects(tmp_path, runner):
    """
    GIVEN: Any config
    WHEN:  We use show --list-objects
    THEN:  The top-level keys are listed.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "alpha:\n  x: 1\nbeta:\n  y: 2\n",
    )
    result = runner.invoke(cli, ["show", "-c", cfg, "--list-objects"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_validate_valid_config(tmp_path, runner):
    """
    GIVEN: Any valid config
    WHEN:  We use validate
    THEN:  success is printed.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "greeter:\n  _type: tests.test_cli_integration.Greeter\n  name: world\n",
    )
    result = runner.invoke(cli, ["validate", "-c", cfg])
    assert result.exit_code == 0
    assert "valid" in result.output.lower()


def test_validate_invalid_config_prints_error(tmp_path, runner):
    """
    GIVEN: Any invalid config
    WHEN:  WE use validate
    THEN:  error is printed.
    """
    cfg = _write_cfg(
        tmp_path,
        "config.yaml",
        "service:\n  _ref: missing_target\n  extra: bad\n",
    )
    result = runner.invoke(cli, ["validate", "-c", cfg])
    assert result.exit_code == 1
    assert "error" in result.output.lower()


def test_missing_object_key_error(tmp_path, runner):
    """
    GIVEN: Any config
    WHEN:  --object refers to a missing key
    THEN:  error lists available keys.
    """
    cfg = _write_cfg(tmp_path, "config.yaml", "db:\n  host: localhost\n")
    result = runner.invoke(cli, ["run", "-c", cfg, "missing"])
    assert result.exit_code == 1
    assert "missing" in result.output
    assert "db" in result.output


def test_set_bad_syntax_error(runner):
    """
    GIVEN: bad/invalid --set syntax
    WHEN:  We use run
    THEN:  error is printed.
    """
    result = runner.invoke(cli, ["run", "-c", "nonexistent.yaml", "x", "--set", "noequals"])
    assert result.exit_code != 0


def test_use_missing_source_error(tmp_path, runner):
    """
    GIVEN: --use with missing source
    WHEN:  We use run
    THEN:  error mentions the path.
    """
    cfg = _write_cfg(tmp_path, "config.yaml", "db:\n  host: localhost\n")
    result = runner.invoke(
        cli,
        ["run", "-c", cfg, "db", "--use", "db.host=nonexistent.path"],
    )
    assert result.exit_code == 1
    assert "nonexistent.path" in result.output


def test_run_with_toml(tmp_path, runner):
    """
    GIVEN: A TOML config
    WHEN:  We use run
    THEN:  It works like just like YAML."""
    cfg = _write_cfg(
        tmp_path,
        "config.toml",
        '[greeter]\n_type = "tests.test_cli_integration.Greeter"\nname = "toml-world"\n',
    )
    result = runner.invoke(cli, ["run", "-c", cfg, "greeter"])
    assert result.exit_code == 0
    assert "Hello, toml-world!" in result.output


if __name__ == "__main__":
    pass
