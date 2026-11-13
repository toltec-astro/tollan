"""Trace contract tests to the sections of a specification document.

Enable the plugin with ``-p tollan.testing.spec_trace`` (for example in the
``addopts`` of the pytest configuration). A test cites the specification
sections it protects with ``@pytest.mark.spec("section-name")`` on the test
itself. A section name is its heading text in lowercase with hyphens; the
document title is not a section. Collection fails when a test cites a section
that the specification does not have, for example after the section was removed
or renamed, and when a ``spec`` marker is placed on a module or class, because
such a marker would cite every test in it.
``--spec_report`` prints, per section, the tests that cite it, the sections no
test cites and the number of uncited tests.

The ``spec_path`` configuration value names the specification, relative to
the pytest root directory: one document, or a folder with an ``index.md`` and
one document per domain. The default is ``design/spec.md``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["read_sections", "section_name"]

SPEC_PATH_DEFAULT = "design/spec.md"
SPEC_INDEX_NAME = "index.md"
_SECTION_HEADING = re.compile(r"^#{2,6}\s+(.+?)\s*$")
_DOMAIN_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def section_name(heading: str) -> str:
    """Return the citation name of a heading text.

    Parameters
    ----------
    heading : str
        The heading text without the leading ``#`` marks.

    Returns
    -------
    str
        The text in lowercase, with each run of characters other than letters
        and digits replaced by one hyphen.

    Examples
    --------
    >>> section_name("Runtime context and component settings")
    'runtime-context-and-component-settings'
    """
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


def read_sections(path: Path) -> list[str]:
    """Read the citable section names of a specification.

    Parameters
    ----------
    path : Path
        The specification document, or a specification folder. In a document,
        headings of level two and below are sections; the document title is
        not. A folder holds ``index.md`` and one document per domain: the
        index title is not a section, and each domain document's title is.

    Returns
    -------
    list of str
        Section names in document order. A folder lists ``index.md`` first,
        then the domain documents in filename order.

    Raises
    ------
    ValueError
        If two headings have the same section name.
    """
    if not path.is_dir():
        documents = [(path, _SECTION_HEADING)]
    else:
        index = path / SPEC_INDEX_NAME
        documents = [(index, _SECTION_HEADING)] if index.is_file() else []
        documents += [
            (p, _DOMAIN_HEADING)
            for p in sorted(path.glob("*.md"))
            if p.name != SPEC_INDEX_NAME
        ]
    sections: list[str] = []
    for document, heading in documents:
        for line in document.read_text().splitlines():
            if not (m := heading.match(line)):
                continue
            name = section_name(m.group(1))
            if name in sections:
                msg = f"{document}: two sections are named {name!r}"
                raise ValueError(msg)
            sections.append(name)
    return sections


_SECTIONS_KEY = pytest.StashKey[list[str]]()
_CITATIONS_KEY = pytest.StashKey[dict[str, list[str]]]()
_UNCITED_KEY = pytest.StashKey[list[str]]()


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add the ``--spec_report`` option and the ``spec_path`` setting."""
    parser.addoption(
        "--spec_report",
        action="store_true",
        help="Report which tests cite each section of the specification.",
    )
    parser.addini(
        "spec_path",
        help="Specification document, relative to the root directory.",
        default=SPEC_PATH_DEFAULT,
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``spec`` marker and read the specification."""
    config.addinivalue_line(
        "markers",
        "spec(*sections): specification sections this test protects",
    )
    try:
        sections = read_sections(config.rootpath / config.getini("spec_path"))
    except ValueError as error:
        raise pytest.UsageError(str(error)) from error
    config.stash[_SECTIONS_KEY] = sections


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Check each test's citations against the specification sections.

    Raises
    ------
    pytest.UsageError
        If a spec marker cites no section or is placed on a module or class,
        or a test cites a section the specification does not have.
    """
    sections = config.stash[_SECTIONS_KEY]
    citations: dict[str, list[str]] = {name: [] for name in sections}
    uncited: list[str] = []
    errors: list[str] = []
    containers: set[str] = set()
    for item in items:
        for node, _ in item.iter_markers_with_node("spec"):
            if node is not item and node.nodeid not in containers:
                containers.add(node.nodeid)
                errors.append(
                    f"{node.nodeid}: spec marker on a {type(node).__name__.lower()}; "
                    "cite sections on each test"
                )
        cited = [s for m in item.iter_markers("spec") for s in m.args]
        if not cited:
            if item.get_closest_marker("spec") is not None:
                errors.append(f"{item.nodeid}: spec marker cites no section")
            uncited.append(item.nodeid)
            continue
        for name in cited:
            if name in citations:
                citations[name].append(item.nodeid)
            else:
                errors.append(f"{item.nodeid}: cites missing section {name!r}")
    if errors:
        raise pytest.UsageError(
            f"Test citations do not match the sections of "
            f"{config.getini('spec_path')}.\n"
            "Re-cite a test only if it protects a current section; otherwise "
            "it protects no requirement.\n  "
            + "\n  ".join(errors)
            + f"\nSections: {', '.join(sections)}"
        )
    config.stash[_CITATIONS_KEY] = citations
    config.stash[_UNCITED_KEY] = uncited


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    """Print the section report when ``--spec_report`` is given."""
    if not config.getoption("spec_report") or _CITATIONS_KEY not in config.stash:
        return
    citations = config.stash[_CITATIONS_KEY]
    uncited = config.stash[_UNCITED_KEY]
    tr = terminalreporter
    tr.section("specification citations")
    for name, nodeids in citations.items():
        tr.write_line(f"{name}: {len(nodeids)} test(s)")
        for nodeid in nodeids:
            tr.write_line(f"    {nodeid}")
    missing = [name for name, nodeids in citations.items() if not nodeids]
    tr.write_line("")
    tr.write_line(f"Sections without a contract test: {', '.join(missing) or 'none'}")
    tr.write_line(f"Tests citing no section: {len(uncited)}")
