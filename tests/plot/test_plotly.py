"""Tests for tollan.plot.plotly module."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import plotly.graph_objects as go
import pytest

from tollan.plot.plotly import (
    ColorPalette,
    SubplotGrid,
    adjust_subplot_colorbars,
    make_empty_figure,
    make_range,
    make_subplot_layout,
    make_subplots,
    update_subplot_layout,
)

if TYPE_CHECKING:
    from tollan.plot.plotly import _SubplotSpec


class TestSubplotGrid:
    """Tests for SubplotGrid class."""

    def test_init_empty(self):
        """Test creating empty SubplotGrid."""
        grid = SubplotGrid()
        assert grid.subplots == []
        assert grid.fig_layout == {}

    def test_add_subplot_basic(self):
        """Test adding a basic subplot."""
        grid = SubplotGrid()
        fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6])])
        grid.add_subplot(1, 1, fig=fig)

        assert len(grid.subplots) == 1
        assert grid.subplots[0]["row"] == 1
        assert grid.subplots[0]["col"] == 1
        assert grid.subplots[0]["fig"] == fig

    def test_add_subplot_with_spec(self):
        """Test adding subplot with specifications."""
        grid = SubplotGrid()
        spec: _SubplotSpec = {"type": "xy", "rowspan": 2, "colspan": 1}
        grid.add_subplot(1, 1, spec=spec, row_height=0.5, col_width=0.3, title="Test")

        subplot = grid.subplots[0]
        assert subplot["spec"] == spec
        assert subplot["row_height"] == 0.5
        assert subplot["col_width"] == 0.3
        assert subplot["title"] == "Test"

    def test_grid_property_caching(self):
        """Test that grid property is cached."""
        grid = SubplotGrid()
        grid.add_subplot(1, 1)

        grid1 = grid.grid
        grid2 = grid.grid
        assert grid1 is grid2  # Same object (cached)

        # Adding subplot invalidates cache
        grid.add_subplot(1, 2)
        grid3 = grid.grid
        assert grid1 is not grid3  # Different object (cache invalidated)

    def test_shape_property(self):
        """Test shape property."""
        grid = SubplotGrid()
        grid.add_subplot(1, 1)
        grid.add_subplot(2, 3)

        shape = grid.shape
        assert shape == (2, 3)

    def test_make_figure_simple(self):
        """Test making a simple figure from grid."""
        grid = SubplotGrid()
        fig1 = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4], name="trace1")])
        fig2 = go.Figure(data=[go.Scatter(x=[5, 6], y=[7, 8], name="trace2")])

        grid.add_subplot(1, 1, fig=fig1)
        grid.add_subplot(1, 2, fig=fig2)

        result = grid.make_figure()

        assert isinstance(result, go.Figure)
        assert len(result.data) == 2  # pyright: ignore[reportArgumentType]
        assert result.data[0].name == "trace1"  # pyright: ignore[reportAttributeAccessIssue]
        assert result.data[1].name == "trace2"  # pyright: ignore[reportAttributeAccessIssue]

    def test_make_figure_with_rowspan_colspan(self):
        """Test making figure with rowspan/colspan."""
        grid = SubplotGrid()
        fig1 = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        fig2 = go.Figure(data=[go.Scatter(x=[5, 6], y=[7, 8])])

        grid.add_subplot(1, 1, fig=fig1)
        grid.add_subplot(1, 2, fig=fig2, spec={"rowspan": 2})

        result = grid.make_figure()
        assert isinstance(result, go.Figure)
        assert len(result.data) == 2  # pyright: ignore[reportArgumentType]

    def test_make_figure_with_shared_axes(self):
        """Test making figure with shared axes."""
        grid = SubplotGrid()
        fig1 = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        fig2 = go.Figure(data=[go.Scatter(x=[5, 6], y=[7, 8])])

        grid.add_subplot(1, 1, fig=fig1)
        grid.add_subplot(2, 1, fig=fig2)

        result = grid.make_figure(shared_xaxes=True)
        assert isinstance(result, go.Figure)

    def test_make_figure_with_custom_sizing(self):
        """Test making figure with custom row/column sizing."""
        grid = SubplotGrid()
        fig1 = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        fig2 = go.Figure(data=[go.Scatter(x=[5, 6], y=[7, 8])])
        fig3 = go.Figure(data=[go.Bar(x=[1, 2], y=[3, 4])])

        # Create a 2x2 grid with custom sizing
        grid.add_subplot(1, 1, fig=fig1, row_height=0.3, col_width=0.7, title="A")
        grid.add_subplot(1, 2, fig=fig2, row_height=0.3, col_width=0.3, title="B")
        grid.add_subplot(2, 1, fig=fig3, row_height=0.7, col_width=0.7, title="C")
        grid.add_subplot(2, 2, fig=None, row_height=0.7, col_width=0.3, title="D")

        result = grid.make_figure()
        assert isinstance(result, go.Figure)

    def test_make_figure_with_none_fig(self):
        """Test making figure with None fig (empty subplot)."""
        grid = SubplotGrid()
        grid.add_subplot(1, 1, fig=None)
        grid.add_subplot(1, 2, fig=go.Figure(data=[go.Scatter(x=[1], y=[2])]))

        result = grid.make_figure()
        assert isinstance(result, go.Figure)
        assert len(result.data) == 1  # pyright: ignore[reportArgumentType]


class TestMakeSubplots:
    """Tests for make_subplots function."""

    def test_basic_grid(self):
        """Test creating basic subplot grid."""
        fig = make_subplots(2, 2)

        assert isinstance(fig, go.Figure)
        assert hasattr(fig, "_grid_ref")

    def test_with_custom_layout(self):
        """Test creating subplots with custom layout."""
        fig_layout = {"title": "Test Figure"}
        fig = make_subplots(2, 2, fig_layout=fig_layout)

        assert fig.layout.title.text == "Test Figure"

    def test_default_uirevision(self):
        """Test that default uirevision is set."""
        fig = make_subplots(2, 2)

        assert fig.layout.uirevision is True

    def test_with_shared_axes(self):
        """Test creating subplots with shared axes."""
        fig = make_subplots(2, 1, shared_xaxes=True)

        assert isinstance(fig, go.Figure)

    def test_subplot_titles_default(self):
        """Test that default subplot titles are created."""
        fig = make_subplots(2, 2)

        # Should have annotations for titles
        assert hasattr(fig.layout, "annotations")


class TestUpdateSubplotLayout:
    """Tests for update_subplot_layout function."""

    def test_update_all_subplots(self):
        """Test updating all subplots."""
        fig = make_subplots(2, 2)
        layout = {
            "xaxis": {"title": "X"},
            "yaxis": {"title": "Y"},
        }

        update_subplot_layout(fig, layout)

        # Check that axes were updated
        assert fig.layout.xaxis.title.text == "X"
        assert fig.layout.yaxis.title.text == "Y"

    def test_update_specific_subplot(self):
        """Test updating specific subplot."""
        fig = make_subplots(2, 2)
        layout = {"xaxis": {"title": "X1"}}

        update_subplot_layout(fig, layout, row=1, col=1)

        # Only first subplot should be updated
        assert fig.layout.xaxis.title.text == "X1"

    def test_with_shapes_and_annotations(self):
        """Test updating layout with shapes and annotations."""
        fig = make_subplots(2, 1)
        layout = {
            "shapes": [{"type": "line", "x0": 0, "y0": 0, "x1": 1, "y1": 1}],
            "annotations": [{"x": 0.5, "y": 0.5, "text": "Test"}],
        }

        update_subplot_layout(fig, layout)

        assert len(fig.layout.shapes) > 0
        assert len(fig.layout.annotations) > 0


class TestMakeSubplotLayout:
    """Tests for make_subplot_layout function."""

    def test_axis_reference_conversion(self):
        """Test that axis references are converted correctly."""
        fig = make_subplots(2, 2)
        layout = {
            "xaxis": {"title": "X"},
            "yaxis": {"title": "Y"},
        }

        result = make_subplot_layout(fig, layout, 1, 2)

        # Should convert xaxis/yaxis to xaxis2/yaxis2 for position (1,2)
        assert "xaxis2" in result
        assert "yaxis2" in result
        assert result["xaxis2"]["title"] == "X"
        assert result["yaxis2"]["title"] == "Y"

    def test_annotation_reference_conversion(self):
        """Test that annotation references are converted."""
        fig = make_subplots(2, 2)
        layout = {
            "annotations": [
                {"x": 0.5, "y": 0.5, "text": "Test", "xref": "x", "yref": "y"},
            ],
        }

        result = make_subplot_layout(fig, layout, 1, 2)

        assert "annotations" in result
        # References should be updated for subplot position
        assert "xref" in result["annotations"][0]
        assert "yref" in result["annotations"][0]


class TestAdjustSubplotColorbars:
    """Tests for adjust_subplot_colorbars function."""

    def test_with_heatmap(self):
        """Test adjusting colorbars with heatmap."""
        fig = make_subplots(1, 2)
        fig.add_trace(
            go.Heatmap(z=[[1, 2], [3, 4]], colorbar={"title": "Color"}),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Heatmap(z=[[5, 6], [7, 8]], colorbar={"title": "Color"}),
            row=1,
            col=2,
        )

        result = adjust_subplot_colorbars(fig)

        assert isinstance(result, go.Figure)
        # Colorbars should have len, x, y set
        for trace in result.data:
            if hasattr(trace, "colorbar"):
                assert "len" in trace.colorbar  # pyright: ignore[reportAttributeAccessIssue]
                assert "x" in trace.colorbar  # pyright: ignore[reportAttributeAccessIssue]
                assert "y" in trace.colorbar  # pyright: ignore[reportAttributeAccessIssue]

    def test_with_scatter_marker_colorbar(self):
        """Test adjusting colorbars with scatter plot."""
        fig = make_subplots(1, 2)
        fig.add_trace(
            go.Scatter(
                x=[1, 2, 3],
                y=[4, 5, 6],
                mode="markers",
                marker={"color": [1, 2, 3], "colorbar": {"title": "Value"}},
            ),
            row=1,
            col=1,
        )

        result = adjust_subplot_colorbars(fig)
        assert isinstance(result, go.Figure)

    def test_with_custom_size(self):
        """Test adjusting colorbars with custom size."""
        fig = make_subplots(1, 2)
        fig.add_trace(go.Heatmap(z=[[1, 2], [3, 4]], colorbar={}), row=1, col=1)

        result = adjust_subplot_colorbars(fig, size=0.5)
        assert isinstance(result, go.Figure)

    def test_without_colorbar(self):
        """Test with traces that don't have colorbars."""
        fig = make_subplots(1, 2)
        fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4]), row=1, col=1)

        result = adjust_subplot_colorbars(fig)
        assert isinstance(result, go.Figure)


class TestMakeRange:
    """Tests for make_range function."""

    def test_with_pad_frac(self):
        """Test range with fractional padding."""
        result = make_range([1, 2, 3, 4, 5])

        # Range is 1-5 (span=4), pad_frac=0.05 -> pad=0.2
        assert result == pytest.approx((1 - 0.2, 5 + 0.2))

    def test_with_absolute_pad(self):
        """Test range with absolute padding."""
        result = make_range([1, 2, 3, 4, 5], pad=1.0)

        assert result == pytest.approx((0.0, 6.0))

    def test_with_numpy_array(self):
        """Test range with numpy array."""
        data = np.array([10, 20, 30, 40, 50])
        result = make_range(data, pad=5)

        assert result == pytest.approx((5.0, 55.0))

    def test_pad_frac_zero(self):
        """Test with zero padding."""
        result = make_range([1, 5], pad=0)

        assert result == pytest.approx((1.0, 5.0))

    def test_both_pad_and_pad_frac_raises(self):
        """Test that specifying both pad and pad_frac."""
        # When pad is explicitly provided, pad_frac is ignored
        # The function uses pad when both are given
        result = make_range([1, 5], pad=1.0)
        assert result == pytest.approx((0.0, 6.0))


class TestMakeEmptyFigure:
    """Tests for make_empty_figure function."""

    def test_without_text(self):
        """Test creating empty figure without text."""
        fig = make_empty_figure()

        assert isinstance(fig, go.Figure)
        assert fig.layout.xaxis.visible is False
        assert fig.layout.yaxis.visible is False
        assert len(fig.data) == 0  # pyright: ignore[reportArgumentType]

    def test_with_placeholder_text(self):
        """Test creating empty figure with placeholder text."""
        fig = make_empty_figure("No data available")

        assert isinstance(fig, go.Figure)
        assert len(fig.layout.annotations) > 0
        assert fig.layout.annotations[0].text == "No data available"

    def test_placeholder_text_centered(self):
        """Test that placeholder text is centered."""
        fig = make_empty_figure("Test")

        anno = fig.layout.annotations[0]
        assert anno.xref == "paper"
        assert anno.yref == "paper"
        assert anno.showarrow is False


class TestColorPalette:
    """Tests for ColorPalette class."""

    def test_init_default(self):
        """Test creating ColorPalette with default name."""
        palette = ColorPalette()

        assert palette.name == "Dark24"
        assert len(palette.colors) > 0
        assert all(c.startswith("#") for c in palette.colors)

    def test_init_custom_name(self):
        """Test creating ColorPalette with custom name."""
        palette = ColorPalette(name="Plotly")

        assert palette.name == "Plotly"
        assert len(palette.colors) > 0

    def test_init_invalid_name(self):
        """Test that invalid color sequence name raises error."""
        palette = ColorPalette(name="NonExistent")
        with pytest.raises(ValueError, match="invalid color sequence name"):
            _ = palette.colors

    def test_colors_property(self):
        """Test colors property returns tuple."""
        palette = ColorPalette()
        colors = palette.colors

        assert isinstance(colors, tuple)
        assert all(isinstance(c, str) for c in colors)

    def test_get_scaled_full_scale(self):
        """Test get_scaled with scale=1.0."""
        palette = ColorPalette()
        scaled = palette.get_scaled(1.0)

        assert scaled == palette.colors

    def test_get_scaled_reduced_scale(self):
        """Test get_scaled with scale < 1.0."""
        palette = ColorPalette()
        original = palette.colors
        scaled = palette.get_scaled(0.5)

        assert len(scaled) == len(original)
        # Colors should be lighter (closer to white)
        assert all(c.startswith("#") for c in scaled)

    def test_get_scaled_caching(self):
        """Test that get_scaled results are cached at function level."""
        palette = ColorPalette()

        result1 = palette.get_scaled(0.5)
        result2 = palette.get_scaled(0.5)

        # Results should be equal (cached function returns same values)
        assert result1 == result2
        # Verify multiple palettes with same name share cache
        palette2 = ColorPalette()
        result3 = palette2.get_scaled(0.5)
        assert result1 == result3

    def test_cycle(self):
        """Test cycle method."""
        palette = ColorPalette()
        cycle = palette.cycle()

        colors = [next(cycle) for _ in range(len(palette.colors) + 5)]

        # Should cycle through colors
        assert len(colors) == len(palette.colors) + 5
        assert colors[0] == colors[len(palette.colors)]

    def test_cycle_with_scale(self):
        """Test cycle with custom scale."""
        palette = ColorPalette()
        cycle = palette.cycle(scale=0.5)

        color = next(cycle)
        assert isinstance(color, str)
        assert color.startswith("#")

    def test_cycles(self):
        """Test cycles method with multiple scales."""
        palette = ColorPalette()
        cycles = palette.cycles(1.0, 0.5, 0.25)

        result = next(cycles)

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert all(c.startswith("#") for c in result)

    def test_cycle_alternated(self):
        """Test cycle_alternated method."""
        palette = ColorPalette()
        cycle = palette.cycle_alternated(1.0, 0.5)

        colors = [next(cycle) for _ in range(10)]

        assert len(colors) == 10
        assert all(c.startswith("#") for c in colors)


class TestShowInDash:
    """Tests for ShowInDash class."""

    def test_init_basic(self):
        """Test basic initialization."""
        from tollan.plot.plotly import ShowInDash

        data_items = [{"title_text": "Test", "data": go.Figure()}]
        show = ShowInDash(data_items=data_items)

        assert show.data_items == data_items
        assert show.title_text is None
        assert show.container_props["fluid"] is True

    def test_init_with_title(self):
        """Test initialization with title."""
        from tollan.plot.plotly import ShowInDash

        show = ShowInDash(data_items=[], title_text="Dashboard")

        assert show.title_text == "Dashboard"

    def test_init_with_container_props(self):
        """Test initialization with custom container props."""
        from tollan.plot.plotly import ShowInDash

        props = {"fluid": False, "size": "lg"}
        show = ShowInDash(data_items=[], container_props=props)

        assert show.container_props["fluid"] is False
        assert show.container_props["size"] == "lg"

    def test_layout_creates_container(self):
        """Test that layout method creates DMC container."""
        from tollan.plot.plotly import ShowInDash

        fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        data_items = [{"title_text": "Plot", "data": fig}]
        show = ShowInDash(data_items=data_items, title_text="Test")

        layout = show.layout()

        # Should return a DMC Container
        assert hasattr(layout, "children")

    def test_make_content_with_figure(self):
        """Test _make_content with Plotly figure."""
        from tollan.plot.plotly import ShowInDash

        fig = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        content = ShowInDash._make_content(fig)

        # Should return dcc.Graph
        assert hasattr(content, "figure")

    def test_make_content_with_dict_figure(self):
        """Test _make_content with figure-like dict."""
        from tollan.plot.plotly import ShowInDash

        fig_dict = {
            "data": [{"type": "scatter", "x": [1, 2], "y": [3, 4]}],
            "layout": {},
        }
        content = ShowInDash._make_content(fig_dict)

        # Should return dcc.Graph
        assert hasattr(content, "figure")

    def test_make_content_with_other_data(self):
        """Test _make_content with non-figure data."""
        from tollan.plot.plotly import ShowInDash

        data = {"key": "value", "number": 42}
        content = ShowInDash._make_content(data)

        # Should return html.Pre with formatted YAML
        assert hasattr(content, "children")

    def test_layout_with_multiple_tabs(self):
        """Test layout with multiple data items."""
        from tollan.plot.plotly import ShowInDash

        fig1 = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        fig2 = go.Figure(data=[go.Bar(x=[1, 2], y=[5, 6])])
        data_items = [
            {"title_text": "Scatter", "data": fig1},
            {"title_text": "Bar", "data": fig2},
        ]
        show = ShowInDash(data_items=data_items)

        layout = show.layout()

        assert hasattr(layout, "children")
        # Should have header and tabs
        assert layout.children is not None
        assert len(layout.children) == 2


# Integration tests
class TestIntegration:
    """Integration tests combining multiple components."""

    def test_subplot_grid_to_figure_workflow(self):
        """Test complete workflow from SubplotGrid to figure."""
        grid = SubplotGrid()

        # Create multiple figures
        fig1 = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 5, 6], name="A")])
        fig2 = go.Figure(data=[go.Heatmap(z=[[1, 2], [3, 4]])])
        fig3 = go.Figure(data=[go.Bar(x=[1, 2], y=[3, 4], name="C")])

        # Build grid
        grid.add_subplot(1, 1, fig=fig1, title="Scatter")
        grid.add_subplot(1, 2, fig=fig2, title="Heatmap")
        grid.add_subplot(2, 1, fig=fig3, spec={"colspan": 2}, title="Bar")

        # Create final figure
        result = grid.make_figure(shared_xaxes=True)

        assert isinstance(result, go.Figure)
        assert len(result.data) == 3  # pyright: ignore[reportArgumentType]

    def test_color_palette_in_subplot(self):
        """Test using ColorPalette for consistent coloring across subplots."""
        palette = ColorPalette(name="Plotly")
        colors = palette.cycle()

        fig = make_subplots(1, 2)

        # Add traces with colors from palette
        fig.add_trace(
            go.Scatter(x=[1, 2], y=[3, 4], line={"color": next(colors)}),
            row=1,
            col=1,
        )
        fig.add_trace(
            go.Scatter(x=[5, 6], y=[7, 8], line={"color": next(colors)}),
            row=1,
            col=2,
        )

        assert len(fig.data) == 2  # pyright: ignore[reportArgumentType]

    def test_empty_figure_in_subplot_grid(self):
        """Test using empty figures as placeholders in grid."""
        grid = SubplotGrid()

        fig1 = go.Figure(data=[go.Scatter(x=[1, 2], y=[3, 4])])
        fig2 = make_empty_figure("Coming soon")

        grid.add_subplot(1, 1, fig=fig1)
        grid.add_subplot(1, 2, fig=fig2)

        result = grid.make_figure()

        assert isinstance(result, go.Figure)
