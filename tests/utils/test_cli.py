"""Tests for tollan.utils.cli module."""

from __future__ import annotations

from tollan.utils.cli import dict_from_cli_args, split_cli_args


class TestDictFromCliArgs:
    """Tests for dict_from_cli_args function."""

    def test_basic_nested_dict(self):
        """Test creating nested dict from CLI args."""
        args = ["--a.b.c", "value"]
        result = dict_from_cli_args(args)

        assert result == {"a": {"b": {"c": "value"}}}

    def test_list_index_syntax(self):
        """Test list syntax with ListDSL extend notation []."""
        args = ["--a.[]", '{"p": "q"}']
        result = dict_from_cli_args(args)

        assert result == {"a": {"[]": {"p": "q"}}}

    def test_boolean_flags(self):
        """Test boolean flag arguments."""
        args = ["--flag1", "--flag2"]
        result = dict_from_cli_args(args)

        assert result == {"flag1": True, "flag2": True}

    def test_yaml_value_parsing(self):
        """Test YAML parsing of values."""
        args = [
            "--number",
            "42",
            "--list",
            "[1, 2, 3]",
            "--dict",
            '{"key": "value"}',
            "--bool",
            "true",
        ]
        result = dict_from_cli_args(args)

        assert result == {
            "number": 42,
            "list": [1, 2, 3],
            "dict": {"key": "value"},
            "bool": True,
        }

    def test_string_values(self):
        """Test string values."""
        args = ["--name", "John", "--message", "Hello World"]
        result = dict_from_cli_args(args)

        assert result == {"name": "John", "message": "Hello World"}

    def test_nested_with_multiple_levels(self):
        """Test deeply nested structure."""
        args = ["--a.b.c.d.e", "deep"]
        result = dict_from_cli_args(args)

        assert result == {"a": {"b": {"c": {"d": {"e": "deep"}}}}}

    def test_mixed_nesting_and_lists(self):
        """Test combination of nesting and list syntax."""
        args = [
            "--items.0.name",
            "first",
            "--items.0.value",
            "10",
            "--items.1.name",
            "second",
            "--items.1.value",
            "20",
        ]
        result = dict_from_cli_args(args)

        assert result == {
            "items": {
                "0": {"name": "first", "value": 10},
                "1": {"name": "second", "value": 20},
            },
        }

    def test_empty_args(self):
        """Test with empty argument list."""
        args = []
        result = dict_from_cli_args(args)

        assert result == {}

    def test_list_dsl_prepend(self):
        """Test ListDSL prepend syntax [:0]."""
        args = ["--items.[:0]", "first"]
        result = dict_from_cli_args(args)

        assert result == {"items": {"[:0]": "first"}}

    def test_list_dsl_slice(self):
        """Test ListDSL slice syntax [1:3]."""
        args = ["--items.[1:3]", "[7, 8]"]
        result = dict_from_cli_args(args)

        assert result == {"items": {"[1:3]": [7, 8]}}

    def test_list_dsl_replace_all(self):
        """Test ListDSL replace all syntax [:]."""
        args = ["--items.[:]", "[new, list]"]
        result = dict_from_cli_args(args)

        assert result == {"items": {"[:]": ["new", "list"]}}

    def test_list_dsl_with_nesting(self):
        """Test ListDSL with nested paths."""
        args = ["--config.items.[]", "value"]
        result = dict_from_cli_args(args)

        assert result == {"config": {"items": {"[]": "value"}}}

    def test_numeric_index_still_works(self):
        """Test that numeric indices still work alongside ListDSL."""
        args = ["--items.0", "first", "--items.1", "second"]
        result = dict_from_cli_args(args)

        assert result == {"items": {"0": "first", "1": "second"}}


class TestSplitCliArgs:
    """Tests for split_cli_args function."""

    def test_basic_split(self):
        """Test basic argument splitting."""
        args = ["--match.a", "value1", "--other.b", "value2"]
        matched, unmatched = split_cli_args(r"match\..+", args)

        assert matched == ["--match.a", "value1"]
        assert unmatched == ["--other.b", "value2"]

    def test_complex_pattern(self):
        """Test with complex regex pattern."""
        args = [
            "--a.0.b",
            "--a.0.c",
            "value",
            "--a.0.d",
            "--a.[]",
            '{"p": "q"}',
            "v0",
            "--",
            "v1",
        ]
        matched, unmatched = split_cli_args(r"a\.0\..+", args)

        assert matched == ["--a.0.b", "--a.0.c", "value", "--a.0.d"]
        assert unmatched == ["--a.[]", '{"p": "q"}', "v0", "--", "v1"]

    def test_no_matches(self):
        """Test when no arguments match pattern."""
        args = ["--foo", "bar", "--baz", "qux"]
        matched, unmatched = split_cli_args(r"nomatch\..+", args)

        assert matched == []
        assert unmatched == args

    def test_all_matches(self):
        """Test when all arguments match pattern."""
        args = ["--prefix.a", "1", "--prefix.b", "2"]
        matched, unmatched = split_cli_args(r"prefix\..+", args)

        assert matched == args
        assert unmatched == []

    def test_positional_separator(self):
        """Test handling of -- positional separator."""
        args = ["--match.a", "value", "--", "--match.b", "value2"]
        matched, unmatched = split_cli_args(r"match\..+", args)

        # The -- is added to unmatched, but matching continues after it
        assert matched == ["--match.a", "value", "--match.b", "value2"]
        assert unmatched == ["--"]

    def test_flags_without_values(self):
        """Test flags without values."""
        args = ["--match.flag1", "--other.flag2", "--match.flag3"]
        matched, unmatched = split_cli_args(r"match\..+", args)

        assert matched == ["--match.flag1", "--match.flag3"]
        assert unmatched == ["--other.flag2"]

    def test_free_floating_values(self):
        """Test free-floating values are unmatched."""
        args = ["value1", "--match.a", "value2", "value3"]
        matched, unmatched = split_cli_args(r"match\..+", args)

        assert matched == ["--match.a", "value2"]
        assert unmatched == ["value1", "value3"]

    def test_empty_args(self):
        """Test with empty argument list."""
        matched, unmatched = split_cli_args(r"pattern", [])

        assert matched == []
        assert unmatched == []

    def test_numeric_args(self):
        """Test that numeric arguments are converted to strings."""
        args = [123, "--match.a", 456]
        matched, unmatched = split_cli_args(r"match\..+", args)  # ty: ignore[invalid-argument-type]

        assert matched == ["--match.a", "456"]
        assert unmatched == ["123"]

    def test_inline_values(self):
        """Test --key=value format is correctly recognized."""
        args = ["--match.a=value1", "--other.b=value2", "--match.c=value3"]
        matched, unmatched = split_cli_args(r"match\..+", args)

        assert matched == ["--match.a=value1", "--match.c=value3"]
        assert unmatched == ["--other.b=value2"]

    def test_mixed_inline_and_separate_values(self):
        """Test mixing --key=value and --key value formats."""
        args = ["--match.a=value1", "--match.b", "value2", "--other.c=value3"]
        matched, unmatched = split_cli_args(r"match\..+", args)

        assert matched == ["--match.a=value1", "--match.b", "value2"]
        assert unmatched == ["--other.c=value3"]
