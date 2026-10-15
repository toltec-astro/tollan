"""Export and display of retained Plotly figures."""

import json
from unittest.mock import Mock

import click
import dash_mantine_components as dmc
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
import pytest
from dash import Dash
from pydantic import ValidationError

from docs.examples.artifact_example import SignalViz
from tollan.plot import plotly as plotly_utils
from tollan.plot.plotly import (
    PlotlyFigExport,
    PlotlyFigExportHtml,
    PlotlyFigExportImage,
    PlotlyFigShowInDash,
)


def test_html_and_json_export_without_reconstruction(tmp_path, monkeypatch):
    viz = SignalViz(save_formats=["html", "json"])
    figure = viz(np.array([1.0, 3.0, 2.0]))
    monkeypatch.setattr(
        SignalViz, "__call__", Mock(side_effect=AssertionError("rebuild"))
    )
    receipts = viz.write(figure, path=tmp_path / "nested" / "signal.v1")
    assert [r.path.name for r in receipts] == ["signal.v1.html", "signal.v1.json"]
    assert [r.format for r in receipts] == ["html", "json"]
    html = receipts[0].path.read_text()
    assert "<html>" in html
    assert "plotly.js" in html
    assert '<script src="https://cdn.plot.ly/' not in html
    assert "Plotly.animate(" not in html
    reopened = pio.read_json(receipts[1].path)
    assert json.loads(reopened.to_json()) == json.loads(figure.to_json())


def test_html_fragment_and_animation_settings(tmp_path):
    figure = go.Figure(
        go.Scatter(y=[1, 2]), frames=[go.Frame(data=[go.Scatter(y=[2, 3])])]
    )
    exporter = PlotlyFigExport(
        html=PlotlyFigExportHtml(full_html=False, include_plotlyjs=False)
    )
    receipt = exporter(tmp_path / "fragment.html", figure)
    saved = receipt.path.read_text()
    assert "<html>" not in saved
    assert "plotly.js" not in saved
    assert "Plotly.animate(" not in saved
    assert "Plotly.addFrames(" in saved


@pytest.mark.parametrize("fmt", ["png", "jpg", "jpeg", "webp", "pdf", "svg"])
def test_image_export_uses_configured_renderer_options(fmt, tmp_path, monkeypatch):
    writer = Mock()
    monkeypatch.setattr(go.Figure, "write_image", writer)
    exporter = PlotlyFigExport(
        image=PlotlyFigExportImage(width=640, height=480, scale=2.0)
    )
    path = tmp_path / f"figure.{fmt}"
    receipt = exporter(path, go.Figure())
    writer.assert_called_once_with(path, format=fmt, width=640, height=480, scale=2.0)
    assert receipt.path == path
    assert receipt.format == fmt


def test_renderer_failure_propagates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        go.Figure, "write_image", Mock(side_effect=RuntimeError("renderer failed"))
    )
    with pytest.raises(RuntimeError, match="renderer failed"):
        PlotlyFigExport()(tmp_path / "failed.png", go.Figure())


def test_invalid_or_disabled_export_does_not_create_destination(tmp_path):
    with pytest.raises(ValueError, match="Unsupported Plotly export format"):
        PlotlyFigExport()(tmp_path / "absent" / "figure.unknown", go.Figure())
    assert not (tmp_path / "absent").exists()
    assert (
        SignalViz(save=False).write(go.Figure(), path=tmp_path / "disabled" / "figure")
        == []
    )
    assert not (tmp_path / "disabled").exists()
    with pytest.raises(ValidationError):
        SignalViz.model_validate({"save_formats": ["unknown"]})
    with pytest.raises(ValidationError):
        PlotlyFigExportImage(width=0)


def test_embed_layout_and_display_same_figure(monkeypatch):
    figure = go.Figure(go.Scatter(y=[1, 2]))
    display = PlotlyFigShowInDash(host="127.0.0.1", port=0)
    app = Dash(__name__)
    app.layout = dmc.MantineProvider(
        display.make_layout({"Signal": figure}, title="Diagnostics")
    )
    response = app.server.test_client().get("/_dash-layout")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["type"] == "MantineProvider"
    assert "Diagnostics" in json.dumps(payload)
    assert '"type": "Graph"' in json.dumps(payload)

    show = Mock()
    monkeypatch.setattr(plotly_utils, "show_in_dash", show)
    display({"Signal": figure}, title="Diagnostics")
    show.assert_called_once_with(
        [{"title_text": "Signal", "data": figure}],
        title_text="Diagnostics",
        host="127.0.0.1",
        port=0,
    )
    show.reset_mock()
    SignalViz(alias="detail", show_plotly=display).show(figure)
    assert show.call_args.args[0][0]["data"] is figure
    assert show.call_args.args[0][0]["title_text"] == "detail"


@pytest.mark.parametrize("interrupted", [False, True])
def test_local_server_releases_resources_on_stop_or_interruption(
    monkeypatch, interrupted
):
    server = Mock(server_port=12345)
    make_server = Mock(return_value=server)
    thread = Mock()
    monkeypatch.setattr(plotly_utils, "make_server", make_server)
    monkeypatch.setattr(plotly_utils.threading, "Thread", Mock(return_value=thread))
    monkeypatch.setattr(
        plotly_utils.click,
        "confirm",
        Mock(side_effect=click.Abort())
        if interrupted
        else Mock(side_effect=[False, True]),
    )
    if interrupted:
        with pytest.raises(click.Abort):
            PlotlyFigShowInDash(port=0)({"Signal": go.Figure()})
    else:
        PlotlyFigShowInDash(port=0)({"Signal": go.Figure()})
    assert make_server.call_args.args[:2] == ("127.0.0.1", 0)
    server.shutdown.assert_called_once_with()
    server.server_close.assert_called_once_with()
    thread.join.assert_called_once_with()


def test_real_static_image_export(tmp_path):
    pytest.importorskip(
        "kaleido", reason="Static export requires optional Kaleido and Chrome"
    )
    figure = SignalViz()(np.array([1.0, 3.0, 2.0]))
    receipt = PlotlyFigExport(image=PlotlyFigExportImage(width=400, height=300))(
        tmp_path / "signal.png", figure
    )
    assert receipt.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
