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

Each Tollan group accepts ``--log_level`` (or ``-l``) with ``DEBUG``, ``INFO``,
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

Tollan's built-in commands
--------------------------

.. typer:: tollan.cli:app
    :prog: tollan
    :width: 80
    :preferred: text
    :show-nested:
