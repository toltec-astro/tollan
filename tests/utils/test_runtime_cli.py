"""Shared path options leave runtime construction to application callbacks."""

from pathlib import Path  # noqa: TC003 -- Typer inspects annotations at runtime
from typing import Annotated, assert_type

import pytest
import typer
from typer.testing import CliRunner

from tollan.config import ConfigSourceFormat, EnvHandler, RuntimeContext
from tollan.utils.typer import TollanTyper, create_cli


def test_command_controls_runtime_construction_and_additional_options(tmp_path):
    app = TollanTyper()
    seen = []
    config = tmp_path / "settings.yaml"
    config.write_text("value: configured\n")

    @app.command()
    @RuntimeContext.add_cli_options()
    def show(
        ctx: typer.Context,
        source: Annotated[Path, typer.Argument()],
        *,
        show_config: bool = False,
    ):
        rc = RuntimeContext.from_cli_ctx(ctx)
        seen.append((rc.config_dict, source, show_config))

    result = CliRunner().invoke(
        app, ["--show_config", "-c", str(config), "--", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert seen[0][0]["value"] == "configured"
    assert seen[0][1:] == (tmp_path, True)


@pytest.mark.parametrize(
    "args", [["--help"], ["--help_all"], ["version"], ["show", "--help"]]
)
def test_help_and_version_do_not_construct_runtime(monkeypatch, args):
    app = create_cli(version="1.2")

    @app.command()
    @RuntimeContext.add_cli_options()
    def show(ctx: typer.Context):
        RuntimeContext.from_cli_ctx(ctx)
        pytest.fail("Command should not run")

    def fail(**kwargs):
        pytest.fail("Runtime should not be constructed")

    monkeypatch.setattr(RuntimeContext, "from_cli", fail)
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    if args == ["version"]:
        assert "1.2" in result.output
    if args == ["show", "--help"]:
        assert "--config_paths" in result.output
        assert "--env_paths" in result.output
        assert "--rc" not in result.output


def test_variadic_inputs_after_separator_remain_untouched(tmp_path):
    app = TollanTyper()
    seen = []
    path = tmp_path / "settings.yaml"
    path.write_text("value: configured\n")

    @app.command()
    @RuntimeContext.add_cli_options()
    def show(ctx: typer.Context, files: Annotated[list[str], typer.Argument()]):
        seen.append((RuntimeContext.from_cli_ctx(ctx).config_dict, files))

    result = CliRunner().invoke(
        app, ["-c", str(path), "--", "a.txt", "--search.pattern", "literal"]
    )
    assert result.exit_code == 0, result.output
    assert seen[0][0]["value"] == "configured"
    assert "search" not in seen[0][0]
    assert seen[0][1] == ["a.txt", "--search.pattern", "literal"]
    missing_separator = CliRunner().invoke(app, ["-c", str(path), "missing.txt"])
    assert missing_separator.exit_code != 0
    assert len(seen) == 1


def test_loading_policy_is_passed_at_runtime_construction(tmp_path):
    app = create_cli()
    seen = []
    directory = tmp_path / "config.d"
    directory.mkdir()
    (directory / "00_settings.yaml").write_text("ignored: true\n")
    (directory / "10_settings.env").write_text("VALUE=text\n")

    @app.command()
    @RuntimeContext.add_cli_options()
    def show(ctx: typer.Context):
        rc = RuntimeContext.from_cli_ctx(
            ctx, config_formats={ConfigSourceFormat.envfile}, env_namespace="process"
        )
        seen.append(rc.config_dict)

    result = CliRunner().invoke(app, ["show", "--config_paths", str(directory)])
    assert result.exit_code == 0, result.output
    assert seen[0]["process"] == {"VALUE": "text"}
    assert "ignored" not in seen[0]
    assert "_env" not in seen[0]


@pytest.mark.parametrize("forward", [False, True])
def test_unconsumed_arguments_are_only_used_when_explicitly_forwarded(forward):
    app = TollanTyper()
    seen = []

    @app.command(
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
    )
    @RuntimeContext.add_cli_options()
    def show(ctx: typer.Context):
        kwargs = {"cli_args": ctx.args} if forward else {}
        seen.append(RuntimeContext.from_cli_ctx(ctx, **kwargs).config_dict)

    result = CliRunner().invoke(app, ["--search.pattern=warning"])
    assert result.exit_code == 0, result.output
    assert ("search" in seen[0]) is forward


@pytest.mark.parametrize("child_paths", [False, True])
def test_root_and_child_have_local_options_without_changing_obj(tmp_path, child_paths):
    app = create_cli()
    seen = []
    root = tmp_path / "root.yaml"
    root.write_text("value: root\n")
    child = tmp_path / "child.yaml"
    child.write_text("value: child\n")
    obj = {"application": True}

    @app.callback()
    @RuntimeContext.add_cli_options()
    def main(ctx: typer.Context, profile: str = "default"):
        assert ctx.obj is obj
        rc = RuntimeContext.from_cli_ctx(ctx)
        rc.update_default_config({"profile": profile})
        seen.append(rc)
        ctx.obj = rc

    @app.command()
    @RuntimeContext.add_cli_options()
    def show(ctx: typer.Context):
        assert ctx.obj is seen[0]
        seen.append(RuntimeContext.from_cli_ctx(ctx))

    args = ["--profile", "local", "-c", str(root), "--", "show"]
    if child_paths:
        args += ["-c", str(child)]
    result = CliRunner().invoke(app, args, obj=obj)
    assert result.exit_code == 0, result.output
    assert seen[0].config_dict["value"] == "root"
    assert seen[0].config_dict["profile"] == "local"
    assert seen[1].config_dict.get("value") == ("child" if child_paths else None)
    assert obj == {"application": True}


def test_adding_options_does_not_require_runtime_or_context_parameter(monkeypatch):
    app = TollanTyper()
    seen = []

    @app.command()
    @RuntimeContext.add_cli_options()
    def show(message: str = "hello"):
        seen.append(message)

    def fail(**kwargs):
        pytest.fail("Runtime should not be constructed")

    monkeypatch.setattr(RuntimeContext, "from_cli", fail)
    assert CliRunner().invoke(app, []).exit_code == 0
    assert seen == ["hello"]


def test_from_cli_ctx_dispatches_to_subclass_and_keeps_invocations_separate():
    class CustomRuntime(RuntimeContext):
        pass

    app = TollanTyper()
    seen = []

    @app.command()
    @CustomRuntime.add_cli_options()
    def show(ctx: typer.Context):
        seen.append(CustomRuntime.from_cli_ctx(ctx))

    runner = CliRunner()
    assert runner.invoke(app, []).exit_code == 0
    seen[0].update_override_config({"value": 1})
    assert runner.invoke(app, []).exit_code == 0
    assert all(isinstance(rc, CustomRuntime) for rc in seen)
    assert "value" not in seen[1].config_dict


def test_source_format_names_match_values():
    assert {fmt.name: fmt.value for fmt in ConfigSourceFormat} == {
        "yaml": "yaml",
        "envfile": "envfile",
        "dict": "dict",
        "list": "list",
    }


@pytest.mark.parametrize("namespace", ["_env", "process", None])
def test_callback_can_request_environment_handler(tmp_path, namespace):
    class CustomRuntime(RuntimeContext):
        pass

    app = TollanTyper()
    path = tmp_path / "settings.env"
    path.write_text("PORT=8000\n")
    seen = []

    @app.command()
    @CustomRuntime.add_cli_options()
    def show(ctx: typer.Context):
        rc, handler = assert_type(
            CustomRuntime.from_cli_ctx(
                ctx, env_namespace=namespace, return_env_handler=True
            ),
            tuple[CustomRuntime, EnvHandler | None],
        )
        assert isinstance(rc, CustomRuntime)
        seen.append(None if handler is None else handler.as_environ())

    result = CliRunner().invoke(app, ["--env_paths", str(path)])
    assert result.exit_code == 0, result.output
    assert seen == [None if namespace is None else {"PORT": "8000"}]
