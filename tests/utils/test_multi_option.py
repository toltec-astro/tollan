"""Tests for MultiOption functionality."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import Annotated

import pytest
import typer
from typer.testing import CliRunner

from tollan.utils.typer import MultiOption


class TestMultiOption:
    """Tests for MultiOption Typer integration."""

    @pytest.fixture
    def runner(self):
        """Provide a CLI runner."""
        return CliRunner()

    def test_basic_multi_option(self, runner):
        """Test basic multi-option with string values."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
        ):
            if values:
                for v in values:
                    typer.echo(v)

        result = runner.invoke(app, ["--values", "a", "b", "c"])
        assert result.exit_code == 0
        assert "a\nb\nc\n" in result.stdout

    def test_multi_option_empty(self, runner):
        """Test multi-option with no values (default)."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
        ):
            typer.echo(f"Values: {values}")

        result = runner.invoke(app, [])
        assert result.exit_code == 0
        assert "Values: None" in result.stdout

    def test_multi_option_with_type_conversion(self, runner):
        """Test multi-option with automatic type conversion."""
        app = typer.Typer()

        @app.command()
        def cmd(
            numbers: Annotated[
                list[float] | None,
                MultiOption(help="Multiple numbers"),
            ] = None,
        ):
            if numbers:
                typer.echo(f"Sum: {sum(numbers)}")

        result = runner.invoke(app, ["--numbers", "1.5", "2.5", "3.0"])
        assert result.exit_code == 0
        assert "Sum: 7.0" in result.stdout

    def test_multi_option_with_path_validation(self, runner, tmp_path):
        """Test multi-option with path validation."""
        # Create test files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("test1")
        file2.write_text("test2")

        app = typer.Typer()

        @app.command()
        def cmd(
            files: Annotated[
                list[Path] | None,
                MultiOption(
                    help="Multiple files",
                    exists=True,
                    dir_okay=False,
                ),
            ] = None,
        ):
            if files:
                for f in files:
                    typer.echo(f"File: {f.name}")

        result = runner.invoke(app, ["--files", str(file1), str(file2)])
        assert result.exit_code == 0
        assert "File: file1.txt" in result.stdout
        assert "File: file2.txt" in result.stdout

    def test_multi_option_path_validation_fails(self, runner, tmp_path):
        """Test multi-option path validation with non-existent file."""
        app = typer.Typer()

        @app.command()
        def cmd(
            files: Annotated[
                list[Path] | None,
                MultiOption(
                    help="Multiple files",
                    exists=True,
                    dir_okay=False,
                ),
            ] = None,
        ):
            pass

        nonexistent = tmp_path / "nonexistent.txt"
        result = runner.invoke(app, ["--files", str(nonexistent)])
        assert result.exit_code != 0
        assert ("does not exist" in result.stdout) or (
            "does not exist" in result.output
        )

    def test_multi_option_stops_at_next_option(self, runner):
        """Test that multi-option stops consuming at next option."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
            *,
            flag: bool = typer.Option(False, "--flag"),  # noqa: FBT003
        ):
            typer.echo(f"Values: {values}")
            typer.echo(f"Flag: {flag}")

        result = runner.invoke(app, ["--values", "a", "b", "--flag"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b']" in result.stdout
        assert "Flag: True" in result.stdout

    def test_multi_option_help_displayed(self, runner):
        """Test that help is correctly displayed for multi-options."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Test help message"),
            ] = None,
        ):
            pass

        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Test help message" in result.stdout
        assert "--values" in result.stdout

    def test_multi_option_int_conversion(self, runner):
        """Test automatic type conversion with integers."""
        app = typer.Typer()

        @app.command()
        def cmd(
            ids: Annotated[
                list[int] | None,
                MultiOption(help="Multiple IDs"),
            ] = None,
        ):
            if ids:
                for id_val in ids:
                    typer.echo(f"ID: {id_val} (type: {type(id_val).__name__})")

        result = runner.invoke(app, ["--ids", "100", "200", "300"])
        assert result.exit_code == 0
        assert "ID: 100 (type: int)" in result.stdout
        assert "ID: 200 (type: int)" in result.stdout

    def test_multi_option_invalid_conversion(self, runner):
        """Test automatic type conversion with invalid values."""
        app = typer.Typer()

        @app.command()
        def cmd(
            numbers: Annotated[
                list[int] | None,
                MultiOption(help="Multiple numbers"),
            ] = None,
        ):
            pass

        result = runner.invoke(app, ["--numbers", "1", "invalid", "3"])
        assert result.exit_code != 0
        # The error message may vary, just check that it failed
        assert ("not a valid integer" in result.output) or (
            "Cannot convert" in result.output
        )

    def test_multiple_multi_options(self, runner):
        """Test command with multiple multi-options."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values1: Annotated[
                list[str] | None,
                MultiOption(help="First set"),
            ] = None,
            values2: Annotated[
                list[str] | None,
                MultiOption(help="Second set"),
            ] = None,
        ):
            typer.echo(f"Values1: {values1}")
            typer.echo(f"Values2: {values2}")

        result = runner.invoke(
            app,
            ["--values1", "a", "b", "--values2", "c", "d"],
        )
        assert result.exit_code == 0
        assert "Values1: ['a', 'b']" in result.stdout
        assert "Values2: ['c', 'd']" in result.stdout

    def test_multi_option_repeated_merged(self, runner):
        """Test that repeated multi-option specifications are merged."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")
                typer.echo(f"Count: {len(values)}")

        result = runner.invoke(
            app,
            ["--values", "a", "--values", "b", "--values", "c", "d"],
        )
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c', 'd']" in result.stdout
        assert "Count: 4" in result.stdout

    def test_multi_option_with_argument_separator(self, runner):
        """Test multi-option with argument separator (--) and positional args."""
        app = typer.Typer()

        @app.command(context_settings={"allow_extra_args": True})
        def cmd(
            ctx: typer.Context,
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")
            if ctx.args:
                typer.echo(f"Args: {ctx.args}")

        result = runner.invoke(app, ["--values", "a", "b", "c", "--", "pos1", "pos2"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c']" in result.stdout
        assert "Args: ['pos1', 'pos2']" in result.stdout

    def test_multi_option_with_fixed_nargs_argument(self, runner):
        """Test multi-option consumes all args until separator or next option."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple option values"),
            ] = None,
            names: Annotated[
                tuple[str, str] | None,
                typer.Argument(help="Exactly two names"),
            ] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")
            if names:
                typer.echo(f"Names: {list(names)}")

        # Without separator: MultiOption consumes everything
        result = runner.invoke(app, ["--values", "a", "b", "c", "name1", "name2"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c', 'name1', 'name2']" in result.stdout
        assert "Names:" not in result.stdout  # No values left for names

        # With separator: MultiOption stops at --
        result = runner.invoke(app, ["--values", "a", "b", "c", "--", "name1", "name2"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c']" in result.stdout
        assert "Names: ['name1', 'name2']" in result.stdout

    def test_multi_option_with_variadic_argument(self, runner):
        """Test multi-option with variadic argument requires separator."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple option values"),
            ] = None,
            files: Annotated[
                list[str] | None,
                typer.Argument(help="Variable number of files"),
            ] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")
            if files:
                typer.echo(f"Files: {files}")
                typer.echo(f"File count: {len(files)}")

        # Without separator: MultiOption consumes all
        result = runner.invoke(app, ["--values", "a", "b", "file1", "file2", "file3"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'file1', 'file2', 'file3']" in result.stdout

        # With separator: Properly split
        result = runner.invoke(
            app,
            ["--values", "a", "b", "--", "file1", "file2", "file3"],
        )
        assert result.exit_code == 0
        assert "Values: ['a', 'b']" in result.stdout
        assert "Files: ['file1', 'file2', 'file3']" in result.stdout
        assert "File count: 3" in result.stdout

    def test_multi_option_between_arguments(self, runner):
        """Test multi-option positioned between arguments with separator."""
        app = typer.Typer()

        @app.command()
        def cmd(
            name: Annotated[str, typer.Argument(help="Name")],
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
            files: Annotated[
                list[str] | None,
                typer.Argument(help="Files"),
            ] = None,
        ):
            typer.echo(f"Name: {name}")
            if values:
                typer.echo(f"Values: {values}")
            if files:
                typer.echo(f"Files: {files}")

        # Argument before option works, but need separator after option
        result = runner.invoke(
            app,
            ["myname", "--values", "a", "b", "c", "--", "file1.txt", "file2.txt"],
        )
        assert result.exit_code == 0
        assert "Name: myname" in result.stdout
        assert "Values: ['a', 'b', 'c']" in result.stdout
        assert "Files: ['file1.txt', 'file2.txt']" in result.stdout

    def test_multiple_multi_options_with_arguments(self, runner):
        """Test multiple multi-options - last one needs separator before arguments."""
        app = typer.Typer()

        @app.command()
        def cmd(
            opt1: Annotated[
                list[str] | None,
                MultiOption(help="First option"),
            ] = None,
            opt2: Annotated[
                list[str] | None,
                MultiOption(help="Second option"),
            ] = None,
            files: Annotated[
                list[str] | None,
                typer.Argument(help="Files"),
            ] = None,
        ):
            if opt1:
                typer.echo(f"Opt1: {opt1}")
            if opt2:
                typer.echo(f"Opt2: {opt2}")
            if files:
                typer.echo(f"Files: {files}")

        # opt1 stops at --opt2, but opt2 needs separator before files
        result = runner.invoke(
            app,
            [
                "--opt1",
                "a",
                "b",
                "--opt2",
                "c",
                "d",
                "--",
                "file1",
                "file2",
            ],
        )
        assert result.exit_code == 0
        assert "Opt1: ['a', 'b']" in result.stdout
        assert "Opt2: ['c', 'd']" in result.stdout
        assert "Files: ['file1', 'file2']" in result.stdout

    def test_multi_option_with_optional_argument(self, runner):
        """Test multi-option with optional argument requires separator."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
            optional_arg: Annotated[
                str | None,
                typer.Argument(help="Optional argument"),
            ] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")
            if optional_arg:
                typer.echo(f"Optional: {optional_arg}")
            else:
                typer.echo("Optional: None")

        # Without separator: MultiOption consumes everything
        result = runner.invoke(app, ["--values", "a", "b", "c", "optional"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c', 'optional']" in result.stdout
        assert "Optional: None" in result.stdout

        # With separator: Properly split
        result = runner.invoke(app, ["--values", "a", "b", "c", "--", "optional"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c']" in result.stdout
        assert "Optional: optional" in result.stdout

        # Without optional argument
        result = runner.invoke(app, ["--values", "a", "b", "c"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c']" in result.stdout
        assert "Optional: None" in result.stdout

    def test_multiple_separators(self, runner):
        """Test multiple separators: --option a b -- file1 file2 -- --option c."""
        app = typer.Typer()

        @app.command()
        def cmd(
            option: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
            files: Annotated[
                list[str] | None,
                typer.Argument(help="Files"),
            ] = None,
        ):
            if option:
                typer.echo(f"Option: {option}")
            if files:
                typer.echo(f"Files: {files}")

        # Multiple separators: first -- stops option, remaining args go to files
        # After first --, everything is treated as positional args
        # (including "--" and "--option")
        result = runner.invoke(
            app,
            ["--option", "a", "b", "--", "file1", "file2", "--", "--option", "c"],
        )
        assert result.exit_code == 0
        assert "Option: ['a', 'b']" in result.stdout
        # After first --, everything is treated as positional args
        # (including "--" and "--option")
        assert "Files: ['file1', 'file2', '--', '--option', 'c']" in result.stdout

    def test_multi_option_with_equals_syntax(self, runner):
        """Test multi-option with --option=value syntax."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")

        # Single --option=value should work
        result = runner.invoke(app, ["--values=a"])
        assert result.exit_code == 0
        assert "Values: ['a']" in result.stdout

        # Multiple with equals: --option=a --option=b
        result = runner.invoke(app, ["--values=a", "--values=b"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b']" in result.stdout

        # Mixed: --option=a --option b c
        result = runner.invoke(app, ["--values=a", "--values", "b", "c"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c']" in result.stdout

    def test_multi_option_equals_syntax_with_positional(self, runner):
        """Test --option= syntax: still consumes following args."""
        app = typer.Typer()

        @app.command()
        def cmd(
            values: Annotated[
                list[str] | None,
                MultiOption(help="Multiple values"),
            ] = None,
            name: Annotated[str | None, typer.Argument()] = None,
        ):
            if values:
                typer.echo(f"Values: {values}")
            if name:
                typer.echo(f"Name: {name}")

        # --option=a --option=b c: By the time parser_process is called,
        # Click has already split --option=b into value='b', so we can't distinguish
        # between --option=b c and --option b c. Both consume until next option.
        result = runner.invoke(app, ["--values=a", "--values=b", "c"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b', 'c']" in result.stdout
        assert "Name:" not in result.stdout

        # To leave c unconsumed, use separator
        result = runner.invoke(app, ["--values=a", "--values=b", "--", "c"])
        assert result.exit_code == 0
        assert "Values: ['a', 'b']" in result.stdout
        assert "Name: c" in result.stdout
