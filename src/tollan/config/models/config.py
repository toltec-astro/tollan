from pydantic import Field, create_model

from ..types import ImmutableBaseModel
from .system_info import SystemInfo


def create_runtime_config_base_model(runtime_info_model_cls=SystemInfo):
    """Return a config base class with given runtime info model."""
    return create_model(
        "RuntimeConfigBaseModel",
        __base__=ImmutableBaseModel,
        runtime_info=(
            runtime_info_model_cls,
            Field(
                default_factory=runtime_info_model_cls,
                description="The runtime info.",
            ),
        ),
    )
