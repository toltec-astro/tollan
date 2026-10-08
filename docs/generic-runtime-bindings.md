# Runtime generic bindings

Bind type arguments when subclassing Tollan's generic bases to select the
schema, mapper, configuration, or context your class will use.

| Task | Generic base | Supply | Available on the subclass |
| --- | --- | --- | --- |
| Define field mappings | `Mapper` / backend mapper | Schema class | `schema` instance |
| Expose a data view | `AccessorBase` / backend accessor | Mapper class | Bound mapper, used by `view.mapper` |
| Validate component settings | `ConfigHandler` | Configuration model | `config_model_cls` |
| Load application settings | `RuntimeContext` | Runtime configuration model | `runtime_config_cls` |
| Select a configuration section | `SubConfigKeyTransformer` | One string `Literal` | `subconfig_key` |
| Configure a pipeline step | `Step` | Configuration and context classes | `config_cls`, `context_cls` |

## Bind a schema to a data view

1. Declare the fields in a schema.
2. Bind the schema to a backend mapper.
3. Bind the mapper to your accessor and expose the values users need.

```{graphviz}
digraph view {
    rankdir=LR;
    node [shape=box];
    SignalSchema -> SignalMapper [label="schema"];
    SignalMapper -> SignalView [label="mapper"];
    "xr.Dataset" -> SignalView [label="data source"];
}
```

```{testcode}
from dataclasses import dataclass

import xarray as xr
from tollan.accessor import Mapping, NameMapping, Schema
from tollan.accessor.xarray import XarrayAccessorBase, XarrayMapper


@dataclass
class SignalSchema(Schema):
    signal: Mapping = NameMapping.var("signal")


class SignalMapper(XarrayMapper[SignalSchema]):
    pass


class SignalView(XarrayAccessorBase[SignalMapper]):
    @property
    def signal(self):
        return self.mapper.get_arr(self.data_source, self.mapper.schema.signal)


view = SignalView(xr.Dataset({"signal": ("sample", [1.0, 2.0])}))
assert view.signal.values.tolist() == [1.0, 2.0]
```

Use the type parameters instead of separately assigning derived class attributes.
For example, `Mapper[SignalSchema]` supplies `schema`; assigning a second `schema`
inside the subclass raises `TypeError`.

See [data adapters](data-adapters.md), [configuration](configuration.md), and
[pipelines](pipelines.md) for complete workflows.

## Define reusable intermediate classes

An intermediate class may forward a type parameter until a concrete subclass
supplies it. Indirect inheritance and nested type expressions are supported:

```{testcode}
from tollan.utils.typing import resolve_generic_bindings


class Store[KeyT, ValueT]:
    pass


class BatchStore[ItemT](Store[str, list[ItemT]]):
    pass


class User:
    pass


class UserBatchStore(BatchStore[User]):
    pass


bindings = resolve_generic_bindings(UserBatchStore, Store)
assert bindings["KeyT"] is str
assert bindings["ValueT"] == list[User]
```

The resulting bindings follow the complete inheritance chain:

```text
UserBatchStore
    └── BatchStore[User]
            └── Store[str, list[User]]
                      KeyT  ValueT
```

| Need | Function | Result |
| --- | --- | --- |
| Inspect inherited type arguments | `resolve_generic_bindings(cls, origin)` | Immutable bindings in the origin's parameter order; unresolved variables may remain. |
| Require concrete, bounded types in a subclass hook | `resolve_concrete_generic_bindings(cls, origin, **requirements)` | Validated bindings, or `None` for a generic intermediate class. |

| Class declaration | Behavior |
| --- | --- |
| Intermediate class forwards a type parameter | Binding waits for specialization. |
| Concrete subclass omits a required type | Raises `TypeError`. |
| Multiple inheritance paths reach the same origin | All paths must agree on the bindings. |
| Type parameter declares a default | Uses the default when omitted. |

Supported: fixed-arity `TypeVar` class hierarchies, including nested type
expressions and Pydantic generic models. `ParamSpec`, `TypeVarTuple`,
instance-level `__orig_class__`, and container-value validation are outside this API.

## Use the policy helper in your own framework

1. Choose the subclass hook: `__init_subclass__` for ordinary classes,
   `__pydantic_init_subclass__` for Pydantic models.
2. Declare each required type parameter and its runtime attribute.
3. Assign the attribute when the helper returns concrete bindings.

```{testcode}
from typing import Any, ClassVar

from pydantic import BaseModel
from tollan.utils.typing import GenericBindingRequirement, resolve_concrete_generic_bindings


class Factory[ModelT: BaseModel](BaseModel):
    model_cls: ClassVar[type[BaseModel]]

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)
        bindings = resolve_concrete_generic_bindings(
            cls, Factory, ModelT=GenericBindingRequirement("model_cls", BaseModel)
        )
        if bindings is not None:
            cls.model_cls = bindings["ModelT"]


class UserModel(BaseModel):
    name: str


class UserFactory(Factory[UserModel]):
    pass


assert Factory[UserModel].model_cls is UserModel
assert UserFactory.model_cls is UserModel
```

The helper validates bindings; the subclass hook assigns the derived attribute.
It rejects explicit assignments that would conflict with the generic declaration.
