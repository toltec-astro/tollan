import itertools
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from functools import cached_property
from typing import TypedDict
from wsgiref.simple_server import make_server

import click
import dash_bootstrap_components as dbc
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html
from dash_component_template import ComponentTemplate
from flask import Flask
from plotly.subplots import make_subplots as _make_subplots

from ..fmt import pformat_yaml
from ..general import rupdate
from ..log import logger


class _SubplotSpec(TypedDict):
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
        row,
        col,
        fig=None,
        spec=None,
        row_height=None,
        col_width=None,
        title=None,
    ):
        """Add figure to the subplots."""
        self.subplots.append(
            {
                "row": row,
                "col": col,
                "fig": fig,
                "spec": spec or {},
                "row_height": row_height,
                "col_width": col_width,
                "title": title,
            },
        )
        # invalid the cache
        if "grid" in self.__dict__:
            del self.__dict__["grid"]

    @cached_property
    def grid(self):
        """The grid."""
        return self._build_grid(self.subplots)

    @property
    def shape(self):
        """The shape of the grid."""
        return self.grid[0].shape

    @classmethod
    def _build_grid(cls, subplots):
        """Return the grid specs and a grid of figures."""

        def _get_grid_indices(s):
            # this covert spec dict to grid slices in x and y.
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

    def make_figure(  # noqa: C901
        self,
        fig_layout=None,
        **kwargs,
    ):
        """Return figure composed from subplots."""
        sxax = kwargs.get("shared_xaxes", None)
        syax = kwargs.get("shared_yaxes", None)
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
        for ckey, key in [
            ("row_heights", "row_height"),
            ("col_widths", "col_width"),
            ("subplot_titles", "title"),
        ]:
            values = [s[-1][key] for s in subplot_locs]
            if all(v is not None for v in values):
                collated_kw[ckey] = values
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
            xax = slayout["xaxis"]
            yax = slayout["yaxis"]
            for k in ("anchor", "domain"):
                xax.pop(k, None)
                yax.pop(k, None)
            if not sxax or row == n_rows:
                fig.update_xaxes(
                    **xax,
                    **panel_kw,
                )
            if not syax or col == 0:
                fig.update_yaxes(
                    **yax,
                    **panel_kw,
                )
        # adjust colorbars
        adjust_subplot_colorbars(fig)
        return fig


def make_subplots(n_rows, n_cols, fig_layout=None, **kwargs):
    """Return a sensible multi-panel figure with predefined layout."""
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


def update_subplot_layout(fig: go.Figure, fig_layout: dict, row=None, col=None):
    """Update fig layout for all subplots."""
    if not hasattr(fig, "_grid_ref"):
        fig.update_layout(**fig_layout)
        return

    grid_ref = fig._grid_ref  # noqa: SLF001

    n_rows, n_cols = len(grid_ref), len(grid_ref[0])
    xaxes = fig_layout.pop("xaxis", {})
    yaxes = fig_layout.pop("yaxis", {})
    fig.update_layout(**fig_layout)

    def _resolve_rowcol(d, n):
        if d is None:
            return range(1, n + 1)
        if isinstance(d, int):
            return [d]
        raise ValueError("invalid row/col.")

    rows = _resolve_rowcol(row, n_rows)
    cols = _resolve_rowcol(col, n_cols)
    for row in rows:
        for col in cols:
            fig.update_xaxes(row=row, col=col, **xaxes)
            fig.update_yaxes(row=row, col=col, **yaxes)
    _fix_scale_anchor(fig["layout"])


def make_subplot_layout(fig: go.Figure, layout: dict, row, col):
    """Return updated layout with correct axes id for subplot."""
    t = go.Scatter()
    fig._set_trace_grid_position(t, row, col)  # noqa: SLF001
    xax = t["xaxis"].lstrip("x")
    yax = t["yaxis"].lstrip("y")
    result = deepcopy(layout)
    x = result.pop("xaxis", None)
    y = result.pop("yaxis", None)
    if x is not None:
        result[f"xaxis{xax}"] = x
    if y is not None:
        result[f"yaxis{yax}"] = y
    _fix_scale_anchor(result)
    return result


def _fix_scale_anchor(layout):
    _layout = layout.to_plotly_json() if isinstance(layout, go.Layout) else layout
    for k, v in _layout.items():
        if k.startswith(("xaxis", "yaxis")) and "scaleanchor" in v:
            layout[k]["scaleanchor"] = v["anchor"]
    return layout


def adjust_subplot_colorbars(fig: go.Figure, size=1.0):
    """Update the figure to correctly place the colorbars for subplots."""
    layout = fig["layout"]
    for i, trace in enumerate(fig["data"]):
        xax = trace["xaxis"].lstrip("x")
        yax = trace["yaxis"].lstrip("y")
        xdom = layout[f"xaxis{xax}"]["domain"]
        ydom = layout[f"yaxis{yax}"]["domain"]
        ysize = ydom[1] - ydom[0]
        cdata = {
            "colorbar": {
                "len": size * ysize,
                "x": xdom[-1] + 0.01,
                "y": ydom[-1] - 0.5 * ysize,
            },
        }
        if trace["type"] not in [
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


def make_range(v, pad=None, pad_frac=0.05):
    """Return the range for data."""
    n_pad_args = sum([pad is None, pad_frac is None])
    if n_pad_args == 0:
        pad = 0
    elif n_pad_args == 2:  # noqa: PLR2004
        raise ValueError("only one of pad and pad_frac can be specified.")
    else:
        pass
    vmin = np.min(v)
    vmax = np.max(v)
    if pad is None:
        pad = pad_frac * (vmax - vmin)
    return vmin - pad, vmax + pad


def make_empty_figure(place_holder_text=None):
    """Return an empty figure."""
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


class ColorPalette:
    """A class to manage colors."""

    name: str
    colors: list

    def __init__(self, name="Dark24"):
        colors = getattr(px.colors.qualitative, name, None)
        if colors is None:
            raise ValueError("invalid color sequence name.")
        self.name = name
        self.colors = colors

    def get_scaled(self, scale):
        """Return scaled colors."""
        colors = self.colors
        if scale >= 1:
            return colors
        return [
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
        ]

    def cycle(self, scale=1):
        """Return color cycle."""
        return itertools.cycle(self.get_scaled(scale))

    def cycles(self, *scales):
        """Return color cycles."""
        return itertools.cycle(
            zip(
                *(self.get_scaled(scale) for scale in scales),
                strict=False,
            ),
        )

    def cycle_alternated(self, *scales):
        """Return color cycles."""
        return itertools.cycle(
            itertools.chain.from_iterable(
                zip(
                    *(self.get_scaled(scale) for scale in scales),
                    strict=False,
                ),
            ),
        )


class ShowInDash(ComponentTemplate):
    """A generic template to render data items for show in dash."""

    _data_items: list

    class Meta:  # noqa: D106
        component_cls = dbc.Container

    def __init__(self, data_items, title_text=None, **kwargs):
        kwargs.setdefault("fluid", True)
        super().__init__(**kwargs)
        self._data_items = data_items
        self._title_text = title_text

    def setup_layout(self, app):
        """Set up the data prod viewr layout."""
        container = self
        header, body = container.grid(2, 1)
        header.child(html.H3, self._title_text or "Show in Dash")

        tabs = body.child(dbc.Tabs)
        for data_item in self._data_items:
            title_text = data_item["title_text"]
            tab = tabs.child(
                dbc.Tab,
                label=title_text,
                tab_id=title_text,
            )
            tab.child(self._make_content(data_item["data"], tab))
        super().setup_layout(app)

    @classmethod
    def _make_content(cls, data, container):
        def _is_figure_like(data):
            if isinstance(data, go.Figure):
                return True
            if isinstance(data, dict) and "data" in data and "layout" in data:
                return True
            return False

        if _is_figure_like(data):
            # graph_style = {"minWidth": "600px"}
            return container.child(
                dcc.Graph,
                figure=data,
                # style=graph_style,
                className="mt-4",
            )
        # fall back to pformat
        return container.child(html.Pre, pformat_yaml(data))


def show_in_dash(data_items, title_text=None, host=None, port=None, **kwargs):
    """Render the figure in dash."""
    keep_alive = True

    server_app = Flask(__name__)
    server = make_server(host or "localhost", port or 8050, server_app)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()

    app = Dash(external_stylesheets=[dbc.themes.COSMO], server=server_app, **kwargs)
    app.enable_dev_tools(debug=True)
    template = ShowInDash(data_items=data_items, title_text=title_text)
    template.setup_layout(app)
    app.layout = template.layout

    def stop_execution():
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
