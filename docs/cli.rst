Command-line applications
=========================

Create an application
---------------------

Use ``create_cli()`` to create a command group with a version command, help,
and logging options:

.. code-block:: python

    from typing import Annotated

    import typer

    from tollan.utils.typer import MultiOption, create_cli

    app = create_cli(version="1.0")

    @app.command()
    def show_files(
        file_names: Annotated[list[str], MultiOption(help="Files to display.")],
    ):
        for name in file_names:
            typer.echo(name)

    if __name__ == "__main__":
        app()

Command and option names match their Python names::

    python app.py show_files --file_names first.txt second.txt
    python app.py version

Use ``TollanTyper()`` when you do not need the version command or the default
group callback. Register commands and nested applications with Typer's
``@app.command()``, ``@app.callback()``, and ``app.add_typer()``.

Option names and values
-----------------------

An option inferred from ``user_name`` is named ``--user_name``. To choose a
different name or add an alias, declare it explicitly:

.. code-block:: python

    user_name: Annotated[str, typer.Option("--user-name", "-u")] = "world"

Boolean options provide both forms, such as
``--show_config`` and ``--no_show_config``.

``MultiOption`` accepts several values after a flag. Repeating the flag adds
more values::

    python app.py show_files --file_names first.txt second.txt --file_names third.txt

Values continue until the next option or ``--``. Put any following positional
arguments after ``--``. The same applies to a child command following a group
option::

    app --env_files one.env two.env -- run

Help
----

Use ``--help`` for the selected command or group. Use ``--help_all`` on a group
to show that group's help plus the full help of its direct children only::

    app --help_all
    app tools --help_all
    app tools convert --help

Each page uses the same formatting as its regular ``--help`` output.

``--help_all`` does not expand grandchildren or run the displayed commands.
Supply any required parent-group options before requesting help for a nested
group.

Logging
-------

Each Tollan group accepts ``--log_level`` with ``DEBUG``, ``INFO``,
or ``WARNING``. The default is ``INFO``. A nested group keeps the current level
unless you supply another one::

    app --log_level DEBUG tools run
    app --log_level DEBUG tools --log_level WARNING run

The first invocation uses DEBUG throughout. The second switches to WARNING
when entering ``tools``.

These group options are also available when a Tollan group is added to another
Typer application::

    host tools --log_level DEBUG run
    host tools --help_all

Place group options before the group's child command. They are not options on
leaf commands; a single-command ``TollanTyper()`` app without a group callback
has only that command's options.

Runtime configuration
---------------------

Add configuration path options with ``RuntimeContext.add_cli_options()`` and
construct a runtime when your callback needs it:

.. code-block:: python

    from typing import Annotated
    import typer

    from tollan.config import RuntimeContext
    from tollan.utils.typer import TollanTyper

    app = TollanTyper()

    @app.command()
    @RuntimeContext.add_cli_options()
    def search(
        ctx: typer.Context,
        files: Annotated[list[str], typer.Argument()],
    ):
        rc = RuntimeContext.from_cli_ctx(ctx)
        print(files, rc.config_dict.get("search"))

This single-command application accepts::

    app --config_paths settings.yaml -- first.txt second.txt

The helper adds ``--config_paths`` (``-c``) and ``--env_paths``. Both accept
multiple values and repeated occurrences. Use ``--`` to end the path options
before positional inputs. Tokens after it remain positional values, including
those beginning with ``--``.

You can apply the same decorator below ``@app.callback()`` to put the options on
a group. Add your other options normally, then call ``from_cli_ctx`` with any
loading settings you need, such as ``env_namespace="process"``. Store the result
on ``ctx.obj`` if child commands should share it.

To accept dotted overrides, configure argument handling explicitly and pass
the configuration arguments as ``cli_args``. For example, a command without
positional arguments can forward its unconsumed options:

.. code-block:: python

    @app.command(
        context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
    )
    @RuntimeContext.add_cli_options()
    def show(ctx: typer.Context):
        rc = RuntimeContext.from_cli_ctx(ctx, cli_args=ctx.args or None)
        print(rc.config_dict.get("search"))

On a command group this accepts::

    app show --config_paths settings.yaml --search.pattern warning

``from_cli_ctx`` does not consume ``ctx.args`` automatically. With variadic
positionals, Typer may collect unknown options among those positional values;
the application must separate overrides before passing them as ``cli_args``.

See :doc:`configuration` for format filtering, dotenv namespaces, and precedence.

Tollan's built-in commands
--------------------------

.. typer:: tollan.cli:app
    :prog: tollan
    :width: 70
    :preferred: text
    :show-nested:
