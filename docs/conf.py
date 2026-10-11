"""Sphinx configuration; inherit the Astropy documentation defaults."""

import warnings
from dataclasses import MISSING
from inspect import signature
from pathlib import Path
from typing import get_type_hints

from docutils import nodes
from pydantic.dataclasses import is_pydantic_dataclass
from sphinx.ext import intersphinx
from sphinx.ext.autodoc import SUPPRESS, AttributeDocumenter
from sphinx.util.inspect import stringify_signature
from sphinx.util.typing import stringify_annotation
from sphinx_astropy.conf.v2 import *  # pyright: ignore[reportWildcardImportFromLibrary]  # noqa: F403
from sphinx_astropy.conf.v2 import (
    exclude_patterns,
    extensions,
)
from sphinxcontrib.autodoc_pydantic.directives.autodocumenters import (
    PydanticFieldDocumenter,
)

import tollan

# -- General configuration ---------------------------------------------

needs_sphinx = "8.2"

# Astropy supplies numpydoc, automodapi, viewcode, and inheritance diagrams.
extensions += [
    "myst_parser",
    "sphinx.ext.doctest",
    "sphinxcontrib.autodoc_pydantic",
    "sphinxcontrib.typer",
]

# Numpydoc's parser emits Python warnings that Sphinx -W does not catch.
# Fail on malformed docstrings instead of silently dropping their content.
warnings.filterwarnings("error", category=UserWarning, module=r"numpydoc\.docscrape$")

# autodoc-pydantic 2.2 requires the Documenter API. With Sphinx 9's default,
# model methods/properties disappear. Remove when the extension supports it.
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html#confval-autodoc_use_legacy_class_based
autodoc_use_legacy_class_based = True
# Use explicit roles for cross-references; ordinary backticks may contain
# parameter names or prose, not Python object names.
default_role = None
myst_heading_anchors = 3
nitpicky = True
# Pytest owns Python docstrings; Sphinx executes the explicit guide examples.
doctest_test_doctest_blocks = ""
# Import the same example classes in guide tests and ordinary pickle round trips.
doctest_path = [str(Path(__file__).parent / "examples")]

# These are non-object labels emitted by generic-base / Pydantic renderers.
# Keep this exact allowlist separate from real public API references.
nitpick_ignore = [
    ("py:obj", "typing.SchemaT"),
    ("py:obj", "typing.MapperT"),
    ("py:obj", "tollan.config.sources.ConfigSourceList.all fields"),
    ("py:obj", "tollan.config.sources.yaml.YamlConfigSource.all fields"),
    ("py:obj", "tollan.config.sources.envfile.EnvFileConfigSource.all fields"),
    ("py:obj", "tollan.config.sources.list_.ListConfigSource.all fields"),
]

# Sphinx's legacy renderer links type parameters as if they were classes.
nitpick_ignore += [
    ("py:class", name)
    for name in (
        "RuntimeInfoT",
        "ConfigT",
        "DataSourceT",
        "MapperT",
        "ContextT",
        "VariableT",
        "ViewT",
        "RuntimeContextT",
        "KeyT",
        "UnitT",
        "F",
        "RootModelRootType",
        "tollan.pipeline.step.ContextT",
        "tollan.pipeline.step.StepT",
    )
]

# Only dependencies used by the public API belong in the cross-reference map.
intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
    "astropy": ("https://docs.astropy.org/en/stable/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "xarray": ("https://docs.xarray.dev/en/stable/", None),
    "pydantic": ("https://docs.pydantic.dev/latest/", None),
    "plotly": ("https://plotly.com/python-api-reference/", None),
    "dask": ("https://docs.dask.org/en/stable/", None),
}

# Base-class annotations can retain import aliases. Resolve them to their public
# names; dependencies without inventories use their official API documentation.
_REFERENCE_ALIASES = {
    "pd.DataFrame": "pandas.DataFrame",
    "pd.Series": "pandas.Series",
    "QDataArray": "xarray.DataArray",
    "MappingABC": "collections.abc.Mapping",
    "Path": "pathlib.Path",
    "npt.NDArray": "numpy.typing.NDArray",
    "npt.ArrayLike": "numpy.typing.ArrayLike",
    "Flag": "enum.Flag",
    "xr.DataArray": "xarray.DataArray",
    "xr.Dataset": "xarray.Dataset",
    "xr.DataTree": "xarray.DataTree",
    "Unit": "astropy.units.Unit",
    "UnitBase": "astropy.units.UnitBase",
    "Quantity": "astropy.units.Quantity",
    "u.Quantity": "astropy.units.Quantity",
    "Time": "astropy.time.Time",
    "PhysicalType": "astropy.units.PhysicalType",
    "QTable": "astropy.table.QTable",
    "Axes": "matplotlib.axes.Axes",
    "np.ma.MaskedArray": "numpy.ma.MaskedArray",
    "np.bool_": "numpy.bool_",
    "np.complexfloating": "numpy.complexfloating",
    "ModuleType": "types.ModuleType",
    "ArgsKwargs": "pydantic_core.ArgsKwargs",
    "ValidationInfo": "pydantic.ValidationInfo",
    # The field renderer requests a class; Pydantic documents this alias as data.
    "pydantic.types.JsonValue": "pydantic.types.JsonValue",
}
_REFERENCE_URLS = {
    "nc.Dataset": "https://unidata.github.io/netcdf4-python/#netCDF4.Dataset",
    "nc.Variable": "https://unidata.github.io/netcdf4-python/#netCDF4.Variable",
    "wrapt.proxies.ObjectProxy": "https://wrapt.readthedocs.io/en/latest/wrappers.html#object-proxy",
    "typer.main.Typer": "https://typer.tiangolo.com/reference/typer/",
    "_wrappers.ObjectProxy": "https://wrapt.readthedocs.io/en/latest/wrappers.html#object-proxy",
    "typer.Context": "https://typer.tiangolo.com/tutorial/commands/context/",
    "typer.models.ParameterInfo": "https://typer.tiangolo.com/reference/parameters/",
    "TypeForm": "https://typing-extensions.readthedocs.io/en/latest/#typing_extensions.TypeForm",
    "dash_mantine_components.Container.Container": "https://www.dash-mantine-components.com/components/container",
    "typer.models.OptionInfo": "https://typer.tiangolo.com/reference/parameters/",
    "yaml.dumper.SafeDumper": "https://pyyaml.org/wiki/PyYAMLDocumentation#dumper",
}

_REFERENCE_URLS.update(
    dict.fromkeys(
        [
            "Node",
            "ScalarNode",
            "yaml.emitter.Emitter",
            "yaml.serializer.Serializer",
            "yaml.representer.SafeRepresenter",
            "yaml.representer.BaseRepresenter",
            "yaml.resolver.Resolver",
            "yaml.resolver.BaseResolver",
        ],
        "https://pyyaml.org/wiki/PyYAMLDocumentation",
    )
)


class _ModelFieldDocumenter(PydanticFieldDocumenter):
    def update_annotations(self, parent):
        # Sphinx 9 copies inherited, source-only Pydantic annotations onto the
        # live model. Later subclasses then fail to resolve names such as Dict.
        # FieldInfo below already supplies the resolved field annotation.
        pass

    # Pydantic has already resolved forward references and Annotated metadata.
    # The upstream documenter instead retries the raw module annotations, which
    # may include TYPE_CHECKING-only names. Keep its defaults/validators/schema.
    def add_directive_header(self, sig):
        self.options.annotation = SUPPRESS
        super().add_directive_header(sig)
        field = self.pydantic.inspect.fields.get(self.pydantic_field_name)

        def field_type():
            pass

        field_type.__annotations__ = {"return": field.annotation}
        mode = (
            "smart"
            if self.config.autodoc_typehints_format == "short"
            else "fully-qualified"
        )
        annotation = stringify_annotation(
            get_type_hints(field_type)["return"], mode=mode
        )
        self.add_line(f"   :type: {annotation}", self.get_sourcename())


class _DataclassFieldDocumenter(AttributeDocumenter):
    # autodoc-pydantic handles BaseModel fields, not Pydantic dataclasses.
    # Sphinx otherwise renders Annotated validation metadata as Python types.
    def add_directive_header(self, sig):
        if (
            not is_pydantic_dataclass(self.parent)
            or self.objpath[-1] not in self.parent.__pydantic_fields__
        ):
            super().add_directive_header(sig)
            return
        annotation_option = self.options.annotation
        self.options.annotation = SUPPRESS
        super().add_directive_header(sig)
        self.options.annotation = annotation_option
        if annotation_option is SUPPRESS:
            return
        if annotation_option:
            self.add_line(f"   :annotation: {annotation_option}", self.get_sourcename())
            return
        if self.config.autodoc_typehints != "none":
            mode = (
                "smart"
                if self.config.autodoc_typehints_format == "short"
                else "fully-qualified"
            )
            annotation = stringify_annotation(
                get_type_hints(self.parent)[self.objpath[-1]], mode=mode
            )
            self.add_line(f"   :type: {annotation}", self.get_sourcename())
        if not self.options.no_value and self.object is not MISSING:
            self.add_line(f"   :value: {self.object!r}", self.get_sourcename())


# Sphinx defines the event callback's positional arguments.
def _dataclass_signature(app, what, name, obj, options, sig, return_annotation):  # noqa: PLR0913, PLR0917
    # Strip Annotated extras in constructor signatures too, without changing the
    # live dataclass annotations used by validation or other documentation pages.
    if what != "class" or not is_pydantic_dataclass(obj):
        return None
    hints = get_type_hints(obj)
    sig = signature(obj)
    sig = sig.replace(
        parameters=[
            parameter.replace(annotation=hints.get(name, parameter.annotation))
            for name, parameter in sig.parameters.items()
        ]
    )
    return (
        stringify_signature(
            sig,
            show_annotation=app.config.autodoc_typehints in {"signature", "both"},
            show_return_annotation=False,
            unqualified_typehints=app.config.autodoc_typehints_format == "short",
            short_literals=app.config.python_display_short_literal_types,
        ),
        return_annotation,
    )


def _resolve_reference_alias(app, env, node, contnode):
    target = node.get("reftarget")
    if target in _REFERENCE_URLS:
        return nodes.reference(
            "", "", contnode, refuri=_REFERENCE_URLS[target], reftitle=target
        )
    if target in _REFERENCE_ALIASES:
        node = node.copy()
        node["reftarget"] = _REFERENCE_ALIASES[target]
        # Annotation aliases may be data entries rather than classes.
        node["reftype"] = "obj"
        return intersphinx.resolve_reference_detect_inventory(env, node, contnode)
    return None


def _configure_documenters(app, config):
    # Sphinx 9 registers its legacy documenters at config-inited, priority 500.
    app.add_autodocumenter(_ModelFieldDocumenter, override=True)
    app.add_autodocumenter(_DataclassFieldDocumenter, override=True)


def setup(app):
    app.connect("config-inited", _configure_documenters, priority=600)
    app.connect("autodoc-process-signature", _dataclass_signature)
    app.connect("missing-reference", _resolve_reference_alias)


# -- Project and output ------------------------------------------------

source_suffix = {".rst": "restructuredtext", ".md": "markdown"}
master_doc = "index"
project = "tollan"
copyright = "2026, Zhiyuan Ma"
author = "Zhiyuan Ma"
version = release = tollan.__version__
language = "en"
exclude_patterns += ["Thumbs.db", ".DS_Store"]
pygments_style = "sphinx"
todo_include_todos = False

html_theme = "sphinx_book_theme"
html_title = "Tollan documentation"
html_static_path = ["_static"]
htmlhelp_basename = "tollandoc"

latex_documents = [
    (
        master_doc,
        "tollan.tex",
        "tollan Documentation",
        "Zhiyuan Ma",
        "manual",
    ),
]


man_pages = [
    (
        master_doc,
        "tollan",
        "tollan Documentation",
        [author],
        1,
    ),
]


texinfo_documents = [
    (
        master_doc,
        "tollan",
        "tollan Documentation",
        author,
        "tollan",
        "Scientific Python utilities.",
        "Miscellaneous",
    ),
]
