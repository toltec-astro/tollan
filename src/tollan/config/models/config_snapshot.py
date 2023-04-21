from pydantic import Field

from ..types import ImmutableBaseModel, TimeField

__all__ = ["ConfigSnapshot"]


class ConfigSnapshot(ImmutableBaseModel):
    """A time-tagged config dict."""

    created_at: TimeField = Field(
        default_factory=TimeField.now,
        description="The creation time",
    )
    config: dict = Field(default_factory=dict, description="The config dict.")
    meta: dict = Field(default_factory=dict, description="Additional meta data.")
