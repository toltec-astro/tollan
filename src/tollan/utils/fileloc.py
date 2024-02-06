import pathlib
import re
import urllib.parse
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import (
    BeforeValidator,
    ConfigDict,
    RootModel,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic.dataclasses import dataclass
from pydantic.networks import Url, UrlConstraints
from pydantic_core import ArgsKwargs

from ..config.types import ImmutableBaseModel
from .general import ensure_abspath


def _url_unquote(
    v: Any,
    _info: ValidationInfo,
):
    if isinstance(v, str):
        _v = v
    elif isinstance(v, Url):
        _v = v.unicode_string()
    else:
        raise TypeError(f"unable to unquote type {type(v)}")
    return urllib.parse.unquote(_v)


_url_attrs = [
    "scheme",
    "host",
    "username",
    "password",
    "port",
    "path",
    "query",
    "fragment",
]


def _url_replace(url, **kwargs):
    def _to_str(d, null_value):
        if d is None:
            return null_value
        return str(d)

    for attr in _url_attrs:
        v = kwargs[attr] if attr in kwargs else getattr(url, attr)
        if attr in [
            "port",
        ]:
            v = TypeAdapter(int | None).validate_python(v)
        elif attr in ["scheme", "host"]:
            v = _to_str(v, null_value="")
        elif attr in ["path"]:
            v = _to_str(v, null_value=None)
        kwargs[attr] = v
    return Url.build(**kwargs)


FileLocUrl = Annotated[
    Url,
    UrlConstraints(allowed_schemes=["file", "http", "https"]),
    BeforeValidator(_url_unquote),
]

_validate_file_loc_url = TypeAdapter(FileLocUrl).validate_python


@dataclass(config=ConfigDict(frozen=True, strit=True))
class FileLocData:
    """A helper model for storing file loc data."""

    url: None | FileLocUrl = None
    path: None | Path = None
    netloc: str = ""
    local_parent_path: None | Path = None
    remote_parent_path: None | Path = None
    url_resolved: None | FileLocUrl = None

    @field_validator("path", "local_parent_path", "remote_parent_path", mode="before")
    @classmethod
    def validate_path(cls, v, _info: ValidationInfo) -> Path:
        """Ensure path instance."""
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("netloc", mode="before")
    @classmethod
    def validate_netloc(cls, v, _info: ValidationInfo) -> Path:
        """Ensure netloc is string."""
        if v is None or v == "localhost":
            return ""
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_arg(cls, values: ArgsKwargs, info: ValidationInfo):
        """Return file loc data from any compatible input.

        Valid forms of inputs are:
        * dict contains keys ``url``, ``path``, ``netloc``;
        * tuple consists of ``(netloc, path)``;
        * str or `Path` instance.
        """
        if isinstance(values, ArgsKwargs):
            # this is invoked with dataclass __init__
            args = values.args or ()
            kwargs = values.kwargs or {}
        else:
            # this is inovked as sub model by pydantic
            args = (values,)
            kwargs = {}
        if len(args) == 0:
            # this will bypass the arg handling and data will be from the kwargs
            arg = None
        elif len(args) == 1:
            # this is single argument, unpack
            arg = args[0]
        elif len(args) == 2:
            # 2-tuple of (netloc, path), will be handled by the code below
            arg = args
        else:
            raise ValueError("expect at most 2 positional arguments.")

        # make sure kwargs does not conflict with arg
        def _set_kwarg(key, value, raise_on_conflict=True):
            if key in kwargs and raise_on_conflict:
                raise ValueError(f"keyword argument {key} not allowed.")
            kwargs[key] = value

        # handle input arg forms
        if arg is None:
            # do nothing
            pass
        elif isinstance(arg, str):
            # try validate as URL
            try:
                url = _validate_file_loc_url(arg)
            except ValidationError:
                if re.match(r"^[A-Z]:\\\w", arg):
                    # local window path
                    _set_kwarg("path", arg)
                elif ":" in arg:
                    # remote path
                    netloc, path = arg.split(":", 1)
                    _set_kwarg("path", path)
                    _set_kwarg("netloc", netloc)
                else:  # local path
                    _set_kwarg("path", arg)
            else:
                # valid url
                _set_kwarg("url", url)
                _set_kwarg("path", url.path)
                _set_kwarg("netloc", url.unicode_host())
        elif isinstance(arg, Path):
            # local path
            _set_kwarg("path", arg)
        elif isinstance(arg, tuple):
            # path with netloc
            if len(arg) == 2:  # noqa: PLR2004
                _set_kwarg("path", arg[1])
                _set_kwarg("netloc", arg[0])
            else:
                raise ValueError(
                    (
                        "file loc tuple requires (netloc, path), got tuple of size"
                        f" {len(arg)}."
                    ),
                )
        elif isinstance(arg, dict):
            for k, v in arg.items():
                _set_kwarg(k, v)
        elif isinstance(arg, (cls, FileLoc)):
            # handle validated instance, just extrtact the fields
            if isinstance(arg, FileLoc):
                arg = arg.root
            for k in arg.__pydantic_fields__:
                _set_kwarg(k, getattr(arg, k))
        else:
            raise TypeError("unknow file loc data type.")
        # update context
        context = info.context or {}
        if "local_parent_path" in context:
            _set_kwarg(
                "local_parent_path",
                context["local_parent_path"],
                raise_on_conflict=False,
            )
        if "remote_parent_path" in context:
            _set_kwarg(
                "remote_parent_path",
                context["remote_parent_path"],
                raise_on_conflict=False,
            )
        return ArgsKwargs(args=(), kwargs=kwargs)

    @model_validator(mode="after")
    def validate_url_resolved(self):
        """Ensure one of URL and path is given, and compute resolved URL."""
        if sum([self.url is not None, self.path is not None]) == 0:
            raise ValueError("url or path required in file loc data.")
        p = self._resolve_path(
            self.netloc,
            self.path,
            local_parent_path=self.local_parent_path,
            remote_parent_path=self.remote_parent_path,
        )
        if self.url is not None:
            url_resolved = _url_replace(self.url, path=p)
        else:
            url_resolved = _url_replace(
                _validate_file_loc_url(p.as_uri()), host=self.netloc
            )
        self.url_resolved = url_resolved
        return self

    @classmethod
    def _resolve_local_path(
        cls,
        path,
        local_parent_path=None,
    ) -> Path:
        p = Path(path)
        if p.is_absolute():
            return p
        # relative path
        if local_parent_path is not None:
            return ensure_abspath(Path(local_parent_path).joinpath(p))
        return ensure_abspath(p)

    @classmethod
    def _resolve_remote_path(
        cls,
        path,
        remote_parent_path=None,
    ) -> Path:
        p = Path(path)
        if isinstance(p, pathlib.WindowsPath):
            # remote window path
            raise TypeError("file loc does not support remote windows path")
        if p.is_absolute():
            # TODO revisit this. may need to resolve anyways
            return p
        # relative path
        if remote_parent_path is None or not Path(remote_parent_path).is_absolute():
            raise ValueError(
                "remote path shall be absolute if no remote_parent_path is set.",
            )
        # TODO note that this may not be fully absolute...
        return Path(remote_parent_path).joinpath(p)

    @classmethod
    def _resolve_path(
        cls,
        hostname,
        path,
        local_parent_path=None,
        remote_parent_path=None,
    ) -> Path:
        if hostname and hostname != "localhost":
            return cls._resolve_remote_path(path, remote_parent_path=remote_parent_path)
        return cls._resolve_local_path(path, local_parent_path=local_parent_path)

    @computed_field
    @cached_property
    def netloc_resolved(self) -> str:
        return self.url_resolved.host or ""

    @computed_field
    @cached_property
    def path_resolved(self) -> Path:
        return Path(self.url_resolved.path)

    @property
    def data_unresolved(self):
        """The unresolved data."""
        if self.url is not None:
            return self.url
        return (self.netloc, self.path)


class FileLoc(RootModel):
    """A model to hold file location info.

    This is a simple wrapper around ``FileLocData``.
    """

    root: FileLocData

    @property
    def url(self) -> str:
        """The resolved URL string."""
        return self.root.url_resolved.unicode_string()

    @property
    def scheme(self) -> str:
        """The URL scheme."""
        return self.root.url_resolved.scheme

    @property
    def host(self) -> str:
        """The host."""
        return self.root.url_resolved.unicode_host() or ""

    @property
    def netloc(self) -> str:
        """The host."""
        return self.host

    @property
    def path(self) -> Path:
        """The path."""
        return Path(self.root.url_resolved.path)

    @property
    def path_orig(self) -> Path | None:
        """The original unresolved path."""
        return self.root.path

    def is_remote(self) -> bool:
        """True if file is remote."""
        return self.netloc not in ["", "localhost"]

    def is_local(self) -> bool:
        """True if file is local."""
        return not self.is_remote()

    def exists(self) -> bool:
        """Check if file is local and exists."""
        return self.is_local() and self.path.exists()

    def as_rsync(self):
        """Return a string suitable to use as rsync argument."""
        if self.is_local():
            return self.path.as_posix()
        return f"{self.netloc}:{self.path}"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.as_rsync()})"


def fileloc(loc, remote_parent_path=None, local_parent_path=None, revalidate=False):
    """Return a validated `FileLoc` object.

    Parameters
    ----------
    loc : str, `~pathlib.Path`, tuple, dict, `FileLoc`

        The file location, either remote or local.
        It can take the form of the follows:

        * URL format string. This is parsed as URL.

        * Non-URL format string.  In this case, `loc` is interpreted as a local path,
          or a remote path similar to sftp syntax: ``<hostname>:<abspath>``.
          A remote relative path is not valid.

        * `~pathlib.Path`. It is a local path.

        * Tuple of ``(<hostname>, <path>)``. It is a remote path, unless
          ``hostname`` is "localhost". A remote relative path is not
          valid.

        * `FileLoc`. It is used as-is if `revalidate` is false, and re-validated with the
          ``data`` attribute otherwise.

    local_parent_path : str, `~pathlib.Path`, None

        If not None, this is used as the parent of local
        relative path. Otherwise, the current path (``pwd``) is used.
        Ignored if `loc` is `~tollan.utils.FileLoc`.

    remote_parent_path : str, `~pathlib.Path`, None

        If not None and is absolute, this is used as the parent of remote
        relative path. Otherwise, `ValueError` will be raised if a remote
        relative path is given.
        Ignored if `loc` is `~tollan.utils.FileLoc`.

    revalidate : bool
        If True and ``loc`` is `FileLoc` object, the data gets re-validated with new
        context.
    """
    _loc = (
        loc.root.data_unresolved if (revalidate and isinstance(loc, FileLoc)) else loc
    )
    return FileLoc.model_validate(
        _loc,
        context={
            "remote_parent_path": remote_parent_path,
            "local_parent_path": local_parent_path,
        },
    )
