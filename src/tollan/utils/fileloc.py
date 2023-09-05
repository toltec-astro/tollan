import pathlib
import re
import urllib.parse
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .general import ensure_abspath
from ..config.types import ImmutableModelBase
from pydantic.networks import Url
from pydantic import model_validator, ValidationInfo, TypeAdapter, BeforeValidator 
from typing import Annotated


def _url_unquote(
    v: Any, info: ValidationInfo
):
    if isinstance(v, str):
        return urllib.parse.unquote(uri_parsed.path)
    v.
    return v

FileLocUrl = Url

_validate_file_loc_url = TypeAdapter(FielLocUrl).validate_python


class FileLoc(ImmutableModelBase):
    """A model to hold file location info.

    The resolved property holds the actual file loc
    as designated by the parent paths specified in the validation
    context.
    """

    url: FileLocUrl
    resolved: None | FileLoc = None

    @model_validator(mode="before")
    @classmethod
    def validate_any(cls, arg: Any, info: ValidationInfo):
        context = info.context
        if isinstance(arg, cls):
            return arg.model_dump()
        if isinstance(arg, dict):
            url = arg.get("url", None)
            path = arg.get("path", None)
            netloc = arg.get("netloc", None)
            resolved = arg.get("resolved", None)
            if sum([url is None, path is None]) == 0:
                raise ValueError("url or path required in file loc data.")
            if url is None:
                loc = (netloc, path)
            else:
                loc = url
        elif isinstance(arg, tuple):
            if len(arg) == 2:
                loc = arg
                resolved = None
            else:
                raise ValueError("netloc and path required in file loc tuple.")
        else:
            loc = arg
            resolved = None
        local_parent_path = context.get("local_parent_path", None)
        remote_parent_path = context.get("remote_parent_path", None)
        url, new_resolved = self._resolve_loc(
            loc,
            resolved,
            local_parent_path=local_parent_path,
            remote_parent_path=remote_parent_path,
        )
        return {"url": url, "resolved": resolved}

    @classmethod
    def _resolve_path(
        cls,
        hostname,
        path,
        local_parent_path=None,
        remote_parent_path=None,
    ) -> Path:
        h = hostname
        p = Path(path)
        if isinstance(p, pathlib.WindowsPath):
            if not h:
                # local window path
                return ensure_abspath(p)
            # remote window path
            raise ValueError("fileloc does not support remote windows path")
        if p.is_absolute():
            # TODO revisit this. may need to resolve anyways
            return p
        # relative path
        # local file
        if not h:
            if local_parent_path is not None:
                return ensure_abspath(Path(local_parent_path).joinpath(p))
            return ensure_abspath(p)
        # remote file
        if remote_parent_path is None or not Path(remote_parent_path).is_absolute():
            raise ValueError(
                "remote path shall be absolute if no remote_parent_path is set.",
            )
        return Path(remote_parent_path).joinpath(p)

    @classmethod
    def _resolve_loc(cls, loc, **kwargs) -> tuple[str, str, Path]:
        if isinstance(loc, str):
            # https://stackoverflow.com/a/57463161/1824372
            if loc.startswith("file://"):
                file_loc_url = _validate_file_loc_url(loc)
                h = uri_parsed.host
                p = urllib.parse.unquote(uri_parsed.path)
                p = cls._resolve_path(h, p, **kwargs)
            elif re.match(r"^[A-Z]:\\\w", loc):
                # local window path
                h = None
                p = cls._resolve_path(h, loc, **kwargs)
                uri = p.as_uri()
            elif ":" in loc:
                h, p = loc.split(":", 1)
                p = cls._resolve_path(h, p, **kwargs)
                uri = str(urlunsplit(urlsplit(p.as_uri())._replace(netloc=h)))
            else:
                # local file
                h = None
                p = cls._resolve_path(h, loc, **kwargs)
                uri = p.as_uri()
        elif isinstance(loc, pathlib.PurePath):
            # local file
            h = None
            p = cls._resolve_path(h, loc, **kwargs)
            uri = p.as_uri()
        elif isinstance(loc, tuple):
            h, p = loc
            p = cls._resolve_path(h, p, **kwargs)
            uri = str(urlunsplit(urlsplit(p.as_uri())._replace(netloc=h)))
        else:
            raise TypeError(f"invalid file location type {loc}.")
        if h is None or h == "localhost":
            h = ""
        return uri, h, p


class FileLoc0:
    """A structure to hold file location info.

    Parameters
    ----------
    args : str, `~pathlib.Path`, `FileLoc`, or tuple of two strings.

        The location of the file, composed of the hostname and the path.
        It can take the form of the follows:

        * ``str``. In this case, `loc` is interpreted as a local path, or a
          remote path similar to sftp syntax: ``<hostname>:<abspath>``.
          A remote relative path is not supported.

        * `~pathlib.Path`. It is a local path.

        * Tuple of ``(<hostname>, <abspath>)``. It is a remote path, unless
          ``hostname`` is "localhost". A remote relative path is not
          supported.

        * `FileLoc`. It is copied with local_parent_path or remote_parent_path resolved.

    local_parent_path : str, `~pathlib.Path`, None

        If not None, this is used as the parent of local
        relative path. Otherwise, the current path (``pwd``) is used.

    remote_parent_path : str, `~pathlib.Path`, None

        If not None and is absolute, this is used as the parent of remote
        relative path. Otherwise, `ValueError` will be raised if a remote
        relative path is given.
    """

    def __init__(self, *args, local_parent_path=None, remote_parent_path=None):
        if len(args) == 1:
            loc = args[0]
        elif len(args) == 2:  # noqa: PLR2004
            loc = args
        elif len(args) == 0:
            raise ValueError("no argument is specified.")
        else:
            raise ValueError("too many arguments.")
        uri, netloc, path = self._resolve_loc(
            loc,
            local_parent_path=local_parent_path,
            remote_parent_path=remote_parent_path,
        )
        self._uri = uri
        self._netloc = netloc
        self._path = path

    @classmethod
    def _resolve_path(
        cls,
        hostname,
        path,
        local_parent_path=None,
        remote_parent_path=None,
    ) -> Path:
        h = hostname
        p = Path(path)
        if isinstance(p, pathlib.WindowsPath):
            if not h:
                # local window path
                return ensure_abspath(p)
            # remote window path
            raise ValueError("fileloc does not support remote windows path")
        if p.is_absolute():
            # TODO revisit this. may need to resolve anyways
            return p
        # relative path
        # local file
        if not h:
            if local_parent_path is not None:
                return ensure_abspath(Path(local_parent_path).joinpath(p))
            return ensure_abspath(p)
        # remote file
        if remote_parent_path is None or not Path(remote_parent_path).is_absolute():
            raise ValueError(
                "remote path shall be absolute if no remote_parent_path is set.",
            )
        return Path(remote_parent_path).joinpath(p)

    @classmethod
    def _resolve_loc(cls, loc, **kwargs) -> tuple[str, str, Path]:
        if isinstance(loc, cls):
            uri = loc.uri
            h = loc.netloc
            p = cls._resolve_path(h, loc.path, **kwargs)
        elif isinstance(loc, str):
            # https://stackoverflow.com/a/57463161/1824372
            if loc.startswith("file://"):
                uri_parsed = urllib.parse.urlparse(loc)
                uri = loc
                h = uri_parsed.netloc
                p = urllib.parse.unquote(uri_parsed.path)
                p = cls._resolve_path(h, p, **kwargs)
            elif re.match(r"^[A-Z]:\\\w", loc):
                # local window path
                h = None
                p = cls._resolve_path(h, loc, **kwargs)
                uri = p.as_uri()
            elif ":" in loc:
                h, p = loc.split(":", 1)
                p = cls._resolve_path(h, p, **kwargs)
                uri = str(urlunsplit(urlsplit(p.as_uri())._replace(netloc=h)))
            else:
                # local file
                h = None
                p = cls._resolve_path(h, loc, **kwargs)
                uri = p.as_uri()
        elif isinstance(loc, pathlib.PurePath):
            # local file
            h = None
            p = cls._resolve_path(h, loc, **kwargs)
            uri = p.as_uri()
        elif isinstance(loc, tuple):
            h, p = loc
            p = cls._resolve_path(h, p, **kwargs)
            uri = str(urlunsplit(urlsplit(p.as_uri())._replace(netloc=h)))
        else:
            raise TypeError(f"invalid file location type {loc}.")
        if h is None or h == "localhost":
            h = ""
        return uri, h, p

    _uri: str
    _netloc: str
    _path: Path

    @property
    def uri(self) -> str:
        """The URI."""
        return self._uri

    @property
    def netloc(self) -> str:
        """The network location."""
        return self._netloc

    @property
    def path(self) -> Path:
        """The path."""
        return self._path

    def exists(self):
        """Check if file is local and exists."""
        return self.is_local and self.path.exists()

    @property
    def is_local(self):
        """Check if file is local."""
        return not self.netloc

    @property
    def is_remote(self):
        """Check if file is remote."""
        return not self.is_local

    def __repr__(self):
        return f"{self.__class__.__name__}({self.as_rsync()})"

    def as_rsync(self):
        """Return a string suitable to use as rsync argument."""
        if self.is_local:
            return self.path.as_posix()
        return f"{self.netloc}:{self.path}"
