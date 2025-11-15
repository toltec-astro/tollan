"""Plotly utilities for multi-panel figures and Dash applications.

Key features:
- SubplotGrid: Stateful builder for complex multi-panel layouts with rowspan/colspan
- adjust_subplot_colorbars: Fix colorbar positioning in subplots
- ColorPalette: Color scaling and cycling for consistent plot styling
- show_in_dash: Quick interactive data visualization in Dash with tabs
"""

from __future__ import annotations

import dataclasses
import functools
import itertools
import threading
from copy import deepcopy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, TypedDict, cast
from wsgiref.simple_server import make_server

import click
import dash_mantine_components as dmc
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html
from flask import Flask
from plotly.subplots import make_subplots as _make_subplots

from ..utils.dict import rupdate
from ..utils.fmt import pformat_yaml
from ..utils.log import logger

__all__ = [
    "ColorPalette",
    "ShowInDash",
    "SubplotGrid",
    "adjust_subplot_colorbars",
    "make_empty_figure",
    "make_range",
    "make_subplot_layout",
    "make_subplots",
    "show_in_dash",
    "update_subplot_layout",
]


class _SubplotSpec(TypedDict, total=False):
    type: str
    rowspan: int
    colspan: int


class _Subplot(TypedDict):
    row: int
    col: int
    fig: None | go.Figure
    spec: _SubplotSpec
    row_height: None | float
    col_width: None | float
    title: None | str


@dataclass
class SubplotGrid:
    """A helper class to build multi panel figure."""

    subplots: list[_Subplot] = field(default_factory=list)
    fig_layout: dict = field(default_factory=dict)

    def add_subplot(  # noqa: PLR0913
        self,
        row: int,
        col: int,
        fig: go.Figure | None = None,
        spec: _SubplotSpec | None = None,
        row_height: float | None = None,
        col_width: float | None = None,
        title: str | None = None,
    ) -> None:
        """Add figure to the subplots.

        Parameters
        ----------
        row : int
            Row index (1-based).
        col : int
            Column index (1-based).
        fig : go.Figure, optional
            Plotly figure to add to this subplot.
        spec : dict, optional
            Subplot specification with type, rowspan, colspan.
        row_height : float, optional
            Relative height of this row.
        col_width : float, optional
            Relative width of this column.
        title : str, optional
            Title for this subplot.
        """
        self.subplots.append(
            {
                "row": row,
                "col": col,
                "fig": fig,
                "spec": spec or _SubplotSpec({}),
                "row_height": row_height,
                "col_width": col_width,
                "title": title,
            },
        )
        # invalid the cache
        if "grid" in self.__dict__:
            del self.__dict__["grid"]

    @cached_property
    def grid(self) -> tuple[Any, list[tuple[slice, slice, _Subplot]]]:
        """The grid specifications and subplot locations.

        Returns
        -------
        tuple[Any, list[tuple[slice, slice, _Subplot]]]
            Grid array and list of (row_slice, col_slice, subplot) tuples
        """
        return self._build_grid(self.subplots)

    @property
    def shape(self) -> tuple[int, int]:
        """The shape of the grid as (n_rows, n_cols).

        Returns
        -------
        tuple[int, int]
            (n_rows, n_cols) dimensions of the subplot grid
        """
        return self.grid[0].shape

    @classmethod
    def _build_grid(
        cls,
        subplots: list[_Subplot],
    ) -> tuple[Any, list[tuple[slice, slice, _Subplot]]]:
        """Build grid specifications from subplot definitions.

        Parameters
        ----------
        subplots : list[_Subplot]
            List of subplot definitions.

        Returns
        -------
        tuple
            Grid array and list of (row_slice, col_slice, subplot) tuples.
        """

        def _get_grid_indices(s):
            # this convert spec dict to grid slices in x and y.
            rs = s["row"] - 1
            re = rs + s["spec"].get("rowspan", 1)
            cs = s["col"] - 1
            ce = cs + s["spec"].get("colspan", 1)
            return rs, re, cs, ce

        subplot_locs = []
        n_rows = 0
        n_cols = 0
        for s in subplots:
            rs, re, cs, ce = _get_grid_indices(s)
            subplot_locs.append((slice(rs, re), slice(cs, ce), s))
            n_rows = max(n_rows, re)
            n_cols = max(n_cols, ce)
        gs = np.full((n_rows, n_cols), {}, dtype=object)
        for xslice, yslice, subplot in subplot_locs:
            gs[xslice, yslice] = None
            gs[xslice.start, yslice.start] = subplot["spec"] or {}
        return gs, subplot_locs

    def make_figure(  # noqa: C901, PLR0912
        self,
        fig_layout: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> go.Figure:
        """Create a figure composed from all subplots.

        Parameters
        ----------
        fig_layout : dict, optional
            Layout dictionary to merge with default layout.
        **kwargs : dict
            Additional arguments passed to make_subplots (e.g., shared_xaxes,
            shared_yaxes, horizontal_spacing, vertical_spacing).

        Returns
        -------
        go.Figure
            Plotly figure with all subplots arranged.
        """
        sxax = kwargs.get("shared_xaxes")
        syax = kwargs.get("shared_yaxes")
        if sxax:
            kwargs.setdefault("vertical_spacing", 0.02)
        if syax:
            kwargs.setdefault("horizontal_spacing", 0.02)
        gs, subplot_locs = self.grid
        n_rows, n_cols = gs.shape
        _fig_layout = deepcopy(self.fig_layout)
        rupdate(_fig_layout, fig_layout or {})
        # collate args
        collated_kw = {}
        # Collect all subplot info
        # (subplot_locs is list of (row_slice, col_slice, subplot_dict))
        subplot_titles = [subplot_dict["title"] for _, _, subplot_dict in subplot_locs]
        if all(t is not None for t in subplot_titles):
            collated_kw["subplot_titles"] = subplot_titles

        # Aggregate row heights and column widths per row/col (not per subplot)
        row_heights_map = {}  # row_idx -> height
        col_widths_map = {}  # col_idx -> width

        for _, _, subplot_dict in subplot_locs:
            row = subplot_dict["row"]
            col = subplot_dict["col"]
            if subplot_dict["row_height"] is not None:
                row_heights_map[row - 1] = subplot_dict["row_height"]
            if subplot_dict["col_width"] is not None:
                col_widths_map[col - 1] = subplot_dict["col_width"]

        # Only set if all rows/cols have values
        if len(row_heights_map) == n_rows:
            collated_kw["row_heights"] = [row_heights_map[i] for i in range(n_rows)]
        if len(col_widths_map) == n_cols:
            collated_kw["column_widths"] = [col_widths_map[i] for i in range(n_cols)]
        fig = make_subplots(
            n_rows,
            n_cols,
            specs=gs.tolist(),
            fig_layout=_fig_layout,
            **(collated_kw | kwargs),
        )
        # now populate the figure with figure in subplots
        for xslice, yslice, subplot in subplot_locs:
            row = xslice.start + 1
            col = yslice.start + 1
            panel_kw = {
                "row": row,
                "col": col,
            }
            sfig = subplot["fig"]
            if sfig is None:
                continue
            # update trace
            for trace in sfig["data"]:
                fig.add_trace(
                    trace,
                    **panel_kw,
                )
            # copy over axis info
            slayout = sfig["layout"].to_plotly_json()
            xax = slayout.get("xaxis", {})
            yax = slayout.get("yaxis", {})
            for k in ("anchor", "domain"):
                xax.pop(k, None)
                yax.pop(k, None)
            if xax and (not sxax or row == n_rows):
                fig.update_xaxes(
                    **xax,
                    **panel_kw,
                )
            if yax and (not syax or col == 0):
                fig.update_yaxes(
                    **yax,
                    **panel_kw,
                )
        # adjust colorbars
        adjust_subplot_colorbars(fig)
        return fig


def make_subplots(
    n_rows: int,
    n_cols: int,
    fig_layout: dict[str, Any] | None = None,
    **kwargs: Any,
) -> go.Figure:
    """Create a multi-panel figure with sensible defaults.

    This is a wrapper around plotly.subplots.make_subplots that applies
    project-specific defaults like uirevision, showlegend, and autorange.

    Parameters
    ----------
    n_rows : int
        Number of rows in the subplot grid.
    n_cols : int
        Number of columns in the subplot grid.
    fig_layout : dict, optional
        Layout dictionary to merge with defaults.
    **kwargs : dict
        Additional arguments passed to plotly.subplots.make_subplots.

    Returns
    -------
    go.Figure
        Plotly figure with subplot grid.

    Examples
    --------
    >>> fig = make_subplots(2, 2, shared_xaxes=True)
    >>> _ = fig.add_trace(go.Scatter(x=[1,2,3], y=[4,5,6]), row=1, col=1)
    """
    _fig_layout = {
        "uirevision": True,
        "showlegend": True,
        "xaxis": {
            "autorange": True,
        },
        "yaxis": {
            "autorange": True,
        },
    }
    if fig_layout is not None:
        rupdate(_fig_layout, fig_layout)
    # this is to allow later updating the titles
    n_panels = n_rows * n_cols
    kwargs.setdefault("subplot_titles", [" " * (i + 1) for i in range(n_panels)])

    fig = _make_subplots(rows=n_rows, cols=n_cols, **kwargs)
    update_subplot_layout(fig, _fig_layout)
    return fig


def update_subplot_layout(
    fig: go.Figure,
    fig_layout: dict[str, Any],
    row: int | None = None,
    col: int | None = None,
) -> None:
    """Update layout for all subplots or specific subplot.

    Parameters
    ----------
    fig : go.Figure
        Plotly figure with subplots.
    fig_layout : dict
        Layout dictionary with xaxis, yaxis, shapes, annotations, etc.
    row : int, optional
        Target row (1-based). If None, updates all rows.
    col : int, optional
        Target column (1-based). If None, updates all columns.

    Notes
    -----
    This function extracts xaxis, yaxis, shapes, and annotations from
    fig_layout and applies them to each subplot using update_xaxes/update_yaxes.
    """
    if not hasattr(fig, "_grid_ref"):
        fig.update_layout(**fig_layout)
        return

    grid_ref = cast("list[list]", fig._grid_ref)

    n_rows, n_cols = len(grid_ref), len(grid_ref[0])
    xaxes = fig_layout.pop("xaxis", {})
    yaxes = fig_layout.pop("yaxis", {})
    shapes = fig_layout.pop("shapes", [])
    annos = fig_layout.pop("annotations", [])
    fig.update_layout(**fig_layout)

    def _resolve_rowcol(d, n):
        if d is None:
            return range(1, n + 1)
        if isinstance(d, int):
            return [d]
        msg = "invalid row/col."
        raise ValueError(msg)

    rows = _resolve_rowcol(row, n_rows)
    cols = _resolve_rowcol(col, n_cols)
    for r in rows:
        for c in cols:
            fig.update_xaxes(row=r, col=c, **xaxes)
            fig.update_yaxes(row=r, col=c, **yaxes)
            for s in shapes:
                fig.add_shape(row=r, col=c, **s)
            for a in annos:
                fig.add_annotation(row=r, col=c, **a)
    _fix_scale_anchor(fig["layout"])  # type: ignore[arg-type]


def make_subplot_layout(
    fig: go.Figure,
    layout: dict[str, Any],
    row: int,
    col: int,
) -> dict[str, Any]:
    """Create layout dict with correct axis references for a specific subplot.

    Parameters
    ----------
    fig : go.Figure
        Plotly figure with subplots.
    layout : dict
        Layout dictionary to adapt for the subplot.
    row : int
        Target row (1-based).
    col : int
        Target column (1-based).

    Returns
    -------
    dict
        Layout dictionary with axis references updated for the subplot.

    Notes
    -----
    Converts xaxis/yaxis to xaxis2/yaxis2 etc. based on subplot position.
    """
    t = go.Scatter()
    fig._set_trace_grid_position(t, row, col)
    xax = cast("str", t["xaxis"]).lstrip("x")
    yax = cast("str", t["yaxis"]).lstrip("y")
    result = deepcopy(layout)
    x = result.pop("xaxis", None)
    y = result.pop("yaxis", None)
    if x is not None:
        result[f"xaxis{xax}"] = x
    if y is not None:
        result[f"yaxis{yax}"] = y
    annos = result.pop("annotations", None)
    if annos is not None:
        for anno in annos:
            for k, a in [("x", xax), ("y", yax)]:
                if f"{k}ref" in anno:
                    anno[f"{k}ref"] = anno[f"{k}ref"].replace(k, f"{k}{a}")
        result["annotations"] = annos
    _fix_scale_anchor(result)
    return result


def _fix_scale_anchor(layout: dict[str, Any] | go.Layout) -> dict[str, Any] | go.Layout:
    """Fix scale anchor references in layout."""
    _layout = layout.to_plotly_json() if isinstance(layout, go.Layout) else layout
    for k, v in _layout.items():
        if k.startswith(("xaxis", "yaxis")) and "scaleanchor" in v:
            layout[k]["scaleanchor"] = v["anchor"]  # type: ignore[index]
    return layout


def adjust_subplot_colorbars(fig: go.Figure, size: float = 1.0) -> go.Figure:
    """Adjust colorbar positions to align with subplot axes.

    Parameters
    ----------
    fig : go.Figure
        Plotly figure with subplots and colorbars.
    size : float, default 1.0
        Fraction of subplot height for colorbar length.

    Returns
    -------
    go.Figure
        Figure with adjusted colorbar positions.

    Notes
    -----
    This function repositions colorbars to align with their corresponding
    subplot's vertical extent, which is particularly useful for multi-panel
    figures where default colorbar positioning can be problematic.
    """
    layout = fig["layout"]
    for i, trace in enumerate(fig["data"]):
        xax = trace["xaxis"].lstrip("x")  # type: ignore[attr-defined]
        yax = trace["yaxis"].lstrip("y")  # type: ignore[attr-defined]
        xdom = cast("list[float]", layout[f"xaxis{xax}"]["domain"])
        ydom = cast("list[float]", layout[f"yaxis{yax}"]["domain"])
        ysize = ydom[1] - ydom[0]
        cdata = {
            "colorbar": {
                "len": size * ysize,
                "x": xdom[-1] + 0.01,
                "y": ydom[-1] - 0.5 * ysize,
            },
        }
        if trace["type"] not in [  # type: ignore[attr-defined]
            "heatmap",
        ]:
            if "colorbar" not in trace:
                continue
            cdata = {"marker": cdata}
        fig.update_traces(
            cdata,
            selector=i,
        )
    return fig


def make_range(
    v: Any,
    pad: float | None = None,
    pad_frac: float = 0.05,
) -> tuple[float, float]:
    """Calculate data range with padding.

    Parameters
    ----------
    v : array-like
        Data values to compute range from.
    pad : float, optional
        Absolute padding to add. If None, uses pad_frac.
    pad_frac : float, default 0.05
        Fractional padding (fraction of data range). Ignored if pad is given.

    Returns
    -------
    tuple[float, float]
        (min_value - padding, max_value + padding)

    Raises
    ------
    ValueError
        If both pad and pad_frac are specified.

    Examples
    --------
    >>> vmin, vmax = make_range([1, 2, 3, 4, 5])
    >>> (float(vmin), float(vmax))
    (0.8, 5.2)
    >>> vmin, vmax = make_range([1, 2, 3, 4, 5], pad=1.0)
    >>> (float(vmin), float(vmax))
    (0.0, 6.0)
    """
    vmin = np.min(v)
    vmax = np.max(v)
    if pad is None:
        pad = pad_frac * (vmax - vmin)
    return vmin - pad, vmax + pad


def make_empty_figure(place_holder_text: str | None = None) -> go.Figure:
    """Create an empty figure with optional placeholder text.

    Parameters
    ----------
    place_holder_text : str, optional
        Text to display in the center of the empty figure.

    Returns
    -------
    go.Figure
        Empty Plotly figure with hidden axes.

    Examples
    --------
    >>> fig = make_empty_figure("No data available")
    >>> fig.show()  # doctest: +SKIP
    """
    fig = go.Figure(
        {
            "layout": {
                "xaxis": {"visible": False},
                "yaxis": {"visible": False},
            },
        },
    )
    fig.update_annotations()
    if place_holder_text:
        fig.add_annotation(
            text=place_holder_text,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 28},
        )
    return fig


@functools.lru_cache(maxsize=128)
def _get_scaled_colors(name: str, scale: float) -> tuple[str, ...]:
    """Get scaled colors from a named palette (cached).

    Parameters
    ----------
    name : str
        Name of the color sequence from plotly.express.colors.qualitative.
    scale : float
        Scaling factor. 1.0 returns original colors, values < 1.0
        blend colors towards white.

    Returns
    -------
    tuple[str, ...]
        Tuple of hex color codes.

    Raises
    ------
    ValueError
        If the color sequence name is invalid.
    """
    colors = getattr(px.colors.qualitative, name, None)
    if colors is None:
        msg = f"invalid color sequence name: {name}"
        raise ValueError(msg)

    if scale >= 1:
        return tuple(colors)

    return tuple(
        "#{:02x}{:02x}{:02x}".format(
            *(
                np.array(
                    px.colors.find_intermediate_color(
                        np.array(px.colors.hex_to_rgb(c)) / 255.0,
                        (1, 1, 1),
                        scale,
                    ),
                )
                * 255.0
            ).astype(int),
        )
        for c in colors
    )


@dataclasses.dataclass
class ColorPalette:
    """A class to manage colors from a named palette."""

    name: str = "Dark24"

    @property
    def colors(self) -> tuple[str, ...]:
        """Tuple of hex color codes in the palette.

        Returns
        -------
        tuple[str, ...]
            Original colors from the palette.
        """
        return _get_scaled_colors(self.name, 1.0)

    def get_scaled(self, scale: float) -> tuple[str, ...]:
        """Get colors scaled by blending with white.

        Parameters
        ----------
        scale : float
            Scaling factor. 1.0 returns original colors, values < 1.0
            blend colors towards white.

        Returns
        -------
        tuple[str, ...]
            Tuple of hex color codes.
        """
        return _get_scaled_colors(self.name, scale)

    def cycle(self, scale: float = 1) -> Iterator[str]:
        """Create an infinite iterator cycling through colors.

        Parameters
        ----------
        scale : float, default 1.0
            Scaling factor for colors (see get_scaled).

        Returns
        -------
        Iterator[str]
            Infinite iterator of hex color codes.
        """
        return itertools.cycle(self.get_scaled(scale))

    def cycles(self, *scales: float) -> Iterator[tuple[str, ...]]:
        """Create iterator cycling through color tuples at different scales.

        Parameters
        ----------
        *scales : float
            Multiple scaling factors.

        Returns
        -------
        Iterator[tuple[str, ...]]
            Iterator of color tuples, one color per scale.
        """
        return itertools.cycle(
            zip(
                *(self.get_scaled(scale) for scale in scales),
                strict=False,
            ),
        )

    def cycle_alternated(self, *scales: float) -> Iterator[str]:
        """Create iterator alternating between colors at different scales.

        Parameters
        ----------
        *scales : float
            Multiple scaling factors.

        Returns
        -------
        Iterator[str]
            Iterator alternating through colors: scale1_color1, scale2_color1,
            scale1_color2, scale2_color2, ...
        """
        return itertools.cycle(
            itertools.chain.from_iterable(
                zip(
                    *(self.get_scaled(scale) for scale in scales),
                    strict=False,
                ),
            ),
        )


@dataclasses.dataclass
class ShowInDash:
    """Dash layout component for displaying data items in tabs.

    This class creates a Dash Mantine Components (DMC) layout with a header
    and tabbed interface for displaying multiple data items (figures or other data).
    """

    data_items: list[dict[str, Any]]
    title_text: str | None = None
    container_props: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.container_props.setdefault("fluid", True)

    def layout(self) -> dmc.Container:
        """Create the data viewer layout with DMC components.

        Returns
        -------
        dmc.Container
            Dash Mantine Components container with header and tabbed content.

        Notes
        -----
        Creates a layout with:
        - Header section with title (dmc.Paper with dmc.Title)
        - Tabbed body section (dmc.Tabs) with one tab per data item
        - Each tab displays either a Plotly figure or formatted YAML
        """
        # Create header with title
        header = dmc.Paper(
            dmc.Title(self.title_text or "Show in Dash", order=3),
            p="md",
            shadow="sm",
            mb="md",
        )

        # Create tabs for data items
        tab_list = []
        tab_panel_list = []

        for i, data_item in enumerate(self.data_items):
            title_text = data_item.get("title_text", f"Tab {i + 1}")
            tab_id = f"tab-{i}"

            # Create tab
            tab_list.append(
                dmc.TabsTab(
                    title_text,
                    value=tab_id,
                ),
            )

            # Create tab panel with content
            tab_panel_list.append(
                dmc.TabsPanel(
                    self._make_content(data_item.get("data")),
                    value=tab_id,
                ),
            )

        # Create tabs component
        tabs = dmc.Tabs(
            [
                dmc.TabsList(tab_list),
                *tab_panel_list,
            ],
            value=tab_list[0].value if tab_list else None,
        )

        # Wrap everything in a container
        return dmc.Container(
            [header, tabs],
            **self.container_props,
        )

    @classmethod
    def _make_content(cls, data: Any) -> dcc.Graph | html.Pre:
        """Create content component for a data item.

        Parameters
        ----------
        data : Any
            Data to display. If it's a Plotly figure (go.Figure or dict with
            'data' and 'layout' keys), creates a dcc.Graph. Otherwise, displays
            formatted YAML.

        Returns
        -------
        dcc.Graph or html.Pre
            Dash component displaying the data.
        """

        def _is_figure_like(data):
            if isinstance(data, go.Figure):
                return True
            return bool(isinstance(data, dict) and "data" in data and "layout" in data)

        if _is_figure_like(data):
            return dcc.Graph(
                figure=data,
                style={"height": "600px"},
            )
        # Fall back to formatted YAML display
        return html.Pre(
            pformat_yaml(data),
            style={
                "backgroundColor": "#f5f5f5",
                "padding": "1rem",
                "borderRadius": "4px",
                "overflow": "auto",
            },
        )


def show_in_dash(
    data_items: list[dict[str, Any]],
    title_text: str | None = None,
    host: str | None = None,
    port: int | None = None,
    **kwargs: Any,
) -> None:
    """Display data items in an interactive Dash application.

    Starts a local Flask server with a Dash app to display data items in tabs.
    The server runs until the user confirms to stop it.

    Parameters
    ----------
    data_items : list[dict]
        List of dictionaries, each containing:
        - 'title_text': str - Tab label
        - 'data': Any - Data to display (Plotly figure or other)
    title_text : str, optional
        Main title displayed at the top of the dashboard.
    host : str, optional
        Server host address. Defaults to 'localhost'.
    port : int, optional
        Server port number. Defaults to 8050.
    **kwargs : dict
        Additional arguments passed to Dash constructor.

    Examples
    --------
    >>> import plotly.graph_objects as go
    >>> fig = go.Figure(data=[go.Scatter(x=[1,2,3], y=[4,5,6])])
    >>> show_in_dash(  # doctest: +SKIP
    ...     [{'title_text': 'My Plot', 'data': fig}],
    ...     title_text='Dashboard'
    ... )
    """
    keep_alive = True

    server_app = Flask(__name__)
    host = host or "localhost"
    port = port or 8050
    server = make_server(host, port, server_app)
    logger.debug(f"created server {host=} {port=}")
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    app = Dash(server=server_app, **kwargs)
    app.enable_dev_tools(debug=True)
    show_in_dash = ShowInDash(data_items=data_items, title_text=title_text)
    app.layout = show_in_dash.layout()

    def stop_execution() -> None:
        nonlocal keep_alive
        keep_alive = False
        server.shutdown()
        server_thread.join()
        logger.debug("flask server shutdown.")

    # start the Dash app in a separate thread
    # def start_dash_app():
    #     app.run_server(debug=False, use_reloader=False, **kwargs)
    # dash_thread = threading.Thread(target=start_dash_app)
    # dash_thread.start()
    while True:
        if click.confirm("Stop dash server and continue?"):
            stop_execution()
            break
    logger.info("server has stopped.")
