"""Pipeline utilities.

Provides two complementary patterns:

1. **Context handler mixins** (:class:`~.context_handler.ContextHandlerMixinBase`,
   :class:`~.context_handler.DictContextHandlerMixin`,
   :class:`~.context_handler.MetadataContextHandlerMixin`) — typed
   storage of context objects in dicts or ``.meta`` attributes.

2. **Step / pipeline system** (:class:`~.step.Step`,
   :class:`~.step.StepConfig`, :class:`~.step.StepContext`,
   :class:`~.step.StepContextDict`, :class:`~.step.SequentialPipeline`) —
   typed, context-aware pipeline steps over ``xr.DataTree`` (or any container
   with ``.attrs``).

Artifact specifications and contexts pair configured artifact construction with
typed access to produced objects. Steps retain these in ``context.artifacts``
for inspection and later materialization.
"""

from .artifact import Artifact, ArtifactContext, ArtifactFile, ArtifactSpec
from .context_handler import (
    ContextHandlerMixinBase,
    DictContextHandlerMixin,
    MetadataContextHandlerMixin,
)
from .step import (
    PIPELINE_CONTEXT_KEY,
    Pipeline,
    SequentialPipeline,
    Step,
    StepConfig,
    StepContext,
    StepContextDict,
    StepFailure,
    StepFailureKind,
    get_pipeline_contexts,
)

__all__ = [
    "PIPELINE_CONTEXT_KEY",
    "Artifact",
    "ArtifactContext",
    "ArtifactFile",
    "ArtifactSpec",
    "ContextHandlerMixinBase",
    "DictContextHandlerMixin",
    "MetadataContextHandlerMixin",
    "Pipeline",
    "SequentialPipeline",
    "Step",
    "StepConfig",
    "StepContext",
    "StepContextDict",
    "StepFailure",
    "StepFailureKind",
    "get_pipeline_contexts",
]
