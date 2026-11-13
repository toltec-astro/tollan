"""Contract tests cite specification sections; stale citations fail collection."""

import pytest

from tollan.testing.spec_trace import read_sections, section_name

SPEC = """\
# Package specification

## Data access

### Read values

## Value types
"""


@pytest.mark.spec("specification-traceability")
def test_section_names_come_from_headings_below_the_title(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text(SPEC)
    assert read_sections(spec) == ["data-access", "read-values", "value-types"]
    assert section_name("Native C++ & tools") == "native-c-tools"


@pytest.mark.spec("specification-traceability")
def test_duplicate_section_names_are_rejected(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("## Read values\n\n### Read Values\n")
    with pytest.raises(ValueError, match="read-values"):
        read_sections(spec)


def _write_folder(root, domains):
    spec = root / "spec"
    spec.mkdir(parents=True)
    (spec / "index.md").write_text("# Package specification\n\n## Purpose\n")
    for name, text in domains.items():
        (spec / f"{name}.md").write_text(text)
    return spec


@pytest.mark.spec("specification-traceability")
def test_folder_sections_include_domain_titles_but_not_the_index_title(tmp_path):
    spec = _write_folder(
        tmp_path,
        {
            "values": "# Value types\n\n## Units\n",
            "access": "# Data access\n\n## Read values\n",
        },
    )
    (spec / "notes.txt").write_text("# Not a domain\n")
    assert read_sections(spec) == [
        "purpose",
        "data-access",
        "read-values",
        "value-types",
        "units",
    ]


@pytest.mark.spec("specification-traceability")
def test_duplicate_section_names_across_folder_documents_are_rejected(tmp_path):
    spec = _write_folder(
        tmp_path,
        {"access": "# Data access\n\n## Units\n", "values": "# Units\n"},
    )
    with pytest.raises(ValueError, match="units"):
        read_sections(spec)


def _run(pytester, *args):
    return pytester.runpytest_subprocess(
        "-p", "tollan.testing.spec_trace", "-p", "no:cacheprovider", *args
    )


@pytest.mark.spec("specification-traceability")
def test_citations_are_checked_and_reported(pytester):
    pytester.makefile(".md", **{"design/spec": SPEC})
    pytester.makepyfile(
        test_cited="""
        import pytest

        @pytest.mark.spec("read-values", "value-types")
        def test_read():
            pass

        def test_helper():
            pass
        """
    )
    result = _run(pytester, "--spec_report")
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(
        [
            "read-values: 1 test(s)",
            "value-types: 1 test(s)",
            "Sections without a contract test: data-access",
            "Tests citing no section: 1",
        ]
    )


@pytest.mark.spec("specification-traceability")
def test_missing_section_fails_collection(pytester):
    pytester.makefile(".md", **{"design/spec": SPEC})
    pytester.makepyfile(
        test_stale="""
        import pytest

        @pytest.mark.spec("removed-section")
        def test_old():
            pass
        """
    )
    result = _run(pytester)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(["*cites missing section 'removed-section'*"])


@pytest.mark.spec("specification-traceability")
def test_module_and_class_citations_fail_collection(pytester):
    pytester.makefile(".md", **{"design/spec": SPEC})
    pytester.makepyfile(
        test_blanket="""
        import pytest

        pytestmark = pytest.mark.spec("data-access")

        def test_one():
            pass

        def test_two():
            pass

        @pytest.mark.spec("value-types")
        class TestValues:
            def test_three(self):
                pass
        """
    )
    result = _run(pytester)
    assert result.ret == pytest.ExitCode.USAGE_ERROR
    result.stderr.fnmatch_lines(
        [
            "*test_blanket.py: spec marker on a module; cite sections on each test",
            "*test_blanket.py::TestValues: spec marker on a class; cite sections*",
        ]
    )
    assert result.stderr.str().count("spec marker on a module") == 1


@pytest.mark.spec("specification-traceability")
def test_specification_path_is_configurable(pytester):
    pytester.makefile(".md", **{"docs/contract": SPEC})
    pytester.makeini("[pytest]\nspec_path = docs/contract.md\n")
    pytester.makepyfile(
        test_cited="""
        import pytest

        @pytest.mark.spec("data-access")
        def test_access():
            pass
        """
    )
    _run(pytester).assert_outcomes(passed=1)


@pytest.mark.spec("specification-traceability")
def test_specification_folder_is_configurable(pytester):
    pytester.makefile(
        ".md",
        **{
            "design/spec/index": "# Package specification\n\n## Purpose\n",
            "design/spec/access": "# Data access\n\n## Read values\n",
        },
    )
    pytester.makeini("[pytest]\nspec_path = design/spec\n")
    pytester.makepyfile(
        test_cited="""
        import pytest

        @pytest.mark.spec("data-access", "read-values")
        def test_access():
            pass
        """
    )
    _run(pytester).assert_outcomes(passed=1)
