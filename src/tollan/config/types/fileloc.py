"""Context-aware Pydantic file-location annotation."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator, ValidationInfo

from ...utils.fileloc import FileLoc, FileLocData

__all__ = ["FileLocField"]


def _prepare_fileloc(value: Any, info: ValidationInfo) -> Any:
    context = info.context or {}
    if (
        context.get("rootpath") is None
        or "local_parent_path" in context
        or isinstance(value, (FileLoc, FileLocData))
        or (isinstance(value, dict) and "local_parent_path" in value)
    ):
        return value
    return FileLoc.model_validate(
        value, context={**context, "local_parent_path": context["rootpath"]}
    )


type FileLocField = Annotated[FileLoc, BeforeValidator(_prepare_fileloc)]
"""A FileLoc using the validation context's rootpath as its local parent.

An explicit local_parent_path, including None, takes precedence over rootpath.
Existing FileLoc and FileLocData instances retain their parent settings.
Other context values, including remote_parent_path, retain FileLoc's behavior.
Without rootpath, validation is the same as for FileLoc.
"""
