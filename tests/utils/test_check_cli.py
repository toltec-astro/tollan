"""Configuration path options pass typed lists directly to the runtime factory."""

import pytest
from typer.testing import CliRunner

from tollan.cli import app
from tollan.config import RuntimeContext


@pytest.mark.parametrize("repeated", [False, True])
def test_check_config_paths_and_env_paths(tmp_path, monkeypatch, repeated):
    config_dir = tmp_path / "config.d"
    config_dir.mkdir()
    (config_dir / "00_base.yaml").write_text("base: true\nvalue: base\n")
    override = tmp_path / "override.yaml"
    override.write_text("value: override\n")
    env_dir = tmp_path / "env.d"
    env_dir.mkdir()
    (env_dir / "00_base.env").write_text("ENV=base\n")
    env_override = tmp_path / "override.env"
    env_override.write_text("ENV=override\n")
    seen = []
    from_cli = RuntimeContext.from_cli

    def capture(**kwargs):
        rc = from_cli(**kwargs)
        seen.append((kwargs, rc.config_dict))
        return rc

    monkeypatch.setattr(RuntimeContext, "from_cli", capture)
    args = ["check"]
    for option, paths in (
        ("--config_paths", [config_dir, override]),
        ("--env_paths", [env_dir, env_override]),
    ):
        args.extend([option, str(paths[0])])
        if repeated:
            args.append(option)
        args.append(str(paths[1]))
    args.extend(["--value", "cli"])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    kwargs, config = seen[0]
    assert kwargs["config_paths"] == [config_dir, override]
    assert kwargs["env_paths"] == [env_dir, env_override]
    assert config["base"] is True
    assert config["value"] == "cli"
    assert config["_env"]["ENV"] == "override"


def test_check_without_paths_passes_none(monkeypatch):
    seen = []
    from_cli = RuntimeContext.from_cli

    def capture(**kwargs):
        seen.append(kwargs)
        return from_cli(**kwargs)

    monkeypatch.setattr(RuntimeContext, "from_cli", capture)
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0, result.output
    assert seen == [
        {
            "config_paths": None,
            "env_paths": None,
            "return_env_handler": False,
            "cli_args": None,
        }
    ]


def test_check_mixed_config_paths(tmp_path, monkeypatch):
    yaml = tmp_path / "defaults.yaml"
    yaml.write_text("workers: 4\n_env: {HOST: localhost}\n")
    env = tmp_path / ".env"
    env.write_text("HOST=example.com\n")
    seen = []
    from_cli = RuntimeContext.from_cli

    def capture(**kwargs):
        rc = from_cli(**kwargs)
        seen.append(rc.config_dict)
        return rc

    monkeypatch.setattr(RuntimeContext, "from_cli", capture)
    result = CliRunner().invoke(
        app,
        ["check", "--config_paths", str(yaml), str(env), "--_env.PORT", "9000"],
    )
    assert result.exit_code == 0, result.output
    assert seen[0]["workers"] == 4
    assert seen[0]["_env"] == {"HOST": "example.com", "PORT": 9000}


def test_check_reports_runtime_failure(monkeypatch):
    def fail(*args, **kwargs):
        msg = "Configuration source unavailable"
        raise RuntimeError(msg)

    monkeypatch.setattr(RuntimeContext, "from_cli_ctx", fail)
    result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 1
    assert "Error: Configuration source unavailable" in result.output
