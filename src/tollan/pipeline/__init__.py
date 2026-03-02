"""Pipeline utilities.

Provides two complementary patterns:

1. **Context handler mixins** (:class:`~.context_handler.ContextHandlerMixinBase`,
   :class:`~.context_handler.DictContextHandlerMixin`,
   :class:`~.context_handler.MetadataContextHandlerMixin`) — low-level typed
   storage of context objects in dicts or ``.meta`` attributes.

2. **Step / pipeline system** (:class:`~.step.Step`,
   :class:`~.step.StepConfig`, :class:`~.step.StepContext`,
   :class:`~.step.StepContextDict`, :class:`~.step.SequentialPipeline`) —
   typed, context-aware pipeline steps over ``xr.DataTree`` (or any container
   with ``.attrs``).
"""

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
    get_pipeline_contexts,
)

__all__ = [
    "PIPELINE_CONTEXT_KEY",
    "ContextHandlerMixinBase",
    "DictContextHandlerMixin",
    "MetadataContextHandlerMixin",
    "Pipeline",
    "SequentialPipeline",
    "Step",
    "StepConfig",
    "StepContext",
    "StepContextDict",
    "get_pipeline_contexts",
]
