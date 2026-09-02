# Runtime generic bindings

This note explains why Tollan derives runtime class attributes from static
generic declarations, how the resolver works, and why the implementation is
local rather than supplied by a dependency.

## The contract

Start with a generic storage interface:

```python
class Store[KeyT, ValueT]:
    pass

class BatchStore[ItemT](Store[str, list[ItemT]]):
    pass

class User:
    pass

class UserBatchStore(BatchStore[User]):
    pass
```

The type checker can determine that `UserBatchStore` ultimately implements
`Store[str, list[User]]`. A framework may also need those two types while the
program is running—for example, to choose a key decoder or a value serializer.
The class declaration should remain the single source of truth rather than
requiring duplicate `key_type` and `value_type` attributes.

Tollan applies this general pattern in the following places:

| Tollan generic origin | Origin type variable | Derived runtime attribute |
| --- | --- | --- |
| `Mapper` | `SchemaT` | `schema` |
| `AccessorBase` | `MapperT` | `_mapper_cls` |
| `ConfigHandler` | `ConfigModelT` | `config_model_cls` |
| `RuntimeContext` | `RuntimeConfigT` | `runtime_config_cls` |
| `SubConfigKeyTransformer` | `KeyT` | `subconfig_key` |
| `Step` | `ConfigT`, `ContextT` | `config_cls`, `context_cls` |

Nothing is resolved during instance construction, validation, mapping, or
pipeline execution. Resolution and materialization happen once, when Python
creates a concrete subclass.

## Why `get_args(cls)` is insufficient

Python erases a user-defined generic alias when it creates a subclass. For
example, `UserBatchStore.__bases__` contains `BatchStore`, not
`BatchStore[User]`. Python preserves the parameterized expression on the
inheritance edge: `types.get_original_bases(UserBatchStore)` returns
`BatchStore[User]`.

The final `Store` types are distributed across two inheritance edges:

```text
UserBatchStore
    |
    | original base expression: BatchStore[User]
    | substitution learned here: ItemT -> User
    v
BatchStore[ItemT]
    |
    | original base expression: Store[str, list[ItemT]]
    | substitute ItemT -> User
    v
Store[str, list[User]]
```

Reading only the first edge works for a direct subclass but cannot answer what
`Store.ValueT` means at the bottom of this chain. Flattening every type found in
every base is also incorrect: it loses which generic class owns each type and
breaks when unrelated generic bases are present.

## Vocabulary

The Python typing specification calls `KeyT` a *type parameter* and `str` in
`Store[str, User]` a *type argument*. Those terms describe syntax well, but are
easy to lose track of while following a value through several inheritance
edges. The resolver therefore uses names based on the role each object has:

| Phrase | Meaning | Example | Question it answers |
| --- | --- | --- | --- |
| **target generic origin** | The exact generic class whose bindings are requested | `Store` | “Which generic class are we resolving?” |
| **origin type variable** | A named type slot declared by the origin | `KeyT`, `ValueT` | “Which origin slot are we resolving?” |
| **supplied type** | A type expression written on one inheritance edge | `User`, `list[ItemT]` | “What did this subclass put in that slot?” |
| **substitution map** | Replacements learned while walking from the concrete class toward the origin | `ItemT -> User` | “What do type variables mean at this point?” |
| **resolved binding** | The final variable-to-type relationship at the target origin | `KeyT -> str`, `ValueT -> list[User]` | “What type did each origin slot become?” |

`GenericBindings` is the immutable result. Its fields are named
`origin`, `type_vars`, and `resolved_types`; named lookup is usually the
clearest interface: `bindings["ValueT"]`. The official parameter/argument
terms only appear where the document discusses Python syntax or external APIs.

## Resolution, step by step

Use the `UserBatchStore` example from above:

```python
class Store[KeyT, ValueT]:
    pass

class BatchStore[ItemT](Store[str, list[ItemT]]):
    pass

class User:
    pass

class UserBatchStore(BatchStore[User]):
    pass
```

Calling `resolve_generic_bindings(UserBatchStore, Store)` performs these steps.

### 1. Identify the origin's type variables

`Store.__type_params__` contains `(KeyT, ValueT)`. The resolver never searches
for “any types that look relevant”; it resolves only this exact origin.

### 2. Start at the inspected class

`UserBatchStore` declares no type variables, so there are initially no known
replacements:

```text
current class = UserBatchStore
substitution map = {}
```

For an intermediate generic class, each declared type variable initially maps
to itself. A PEP 696 default maps to its default type instead.

### 3. Read one original inheritance edge

`types.get_original_bases(UserBatchStore)` supplies `BatchStore[User]`.
`typing.get_origin` and `typing.get_args` split that expression into its class
and supplied type:

| Type variable on `BatchStore` | Supplied type | New substitution |
| --- | --- | --- |
| `ItemT` | `User` | `ItemT -> User` |

### 4. Substitute while crossing the next edge

The original base of `BatchStore` is `Store[str, list[ItemT]]`. Substitution is
recursive, so the known replacement is also applied inside `list`:

```text
str         -> str
list[ItemT] -> list[User]
```

The resolved bindings at `Store` are therefore:

```text
KeyT   -> str
ValueT -> list[User]
```

### 5. Return the exact-origin result

The path reached `Store`, so the result retains `Store`'s declaration order:

```python
bindings = resolve_generic_bindings(UserBatchStore, Store)
assert bindings.resolved_types == (str, list[User])
assert bindings["ValueT"] == list[User]
```

### 6. Reconcile multiple paths

Python permits a diamond in which more than one inheritance path reaches the
same target generic origin:

```text
              Store[str, User]
                 /         \
              Left         Right
                 \         /
                   Diamond
```

The resolver deliberately walks every path that reaches `Store`. If both paths
produce the same resolved origin bindings, the diamond is harmless. If one path
produces `Store[str, User]` and the other produces `Store[int, User]`, class
creation fails with both paths in the error. Choosing the first path silently
would make runtime behavior depend on base ordering.

Class inheritance graphs cannot contain cycles, so the path walker does not
need an arbitrary depth limit or a complex global visited cache.

## The two implementation layers

The code separates graph mechanics from Tollan framework policy.

### Layer 1: describe the inheritance graph

`resolve_generic_bindings(cls, origin)`:

- has no side effects;
- uses only public Python introspection APIs;
- substitutes type variables through every relevant inheritance edge;
- retains unresolved type variables for intermediate generic classes;
- reports ambiguous diamonds.

This is the necessarily technical part. It answers only “what type does this
class ultimately resolve for each type variable of this exact origin?”

### Layer 2: apply the common class-creation policy

`resolve_concrete_generic_bindings` centralizes the checks previously repeated
in every consumer:

1. reject an explicitly assigned runtime attribute;
2. allow a genuinely generic intermediate class to defer materialization;
3. reject a bare concrete subclass with a missing required type;
4. optionally require the resolved type to be a subclass of a runtime base.

An accessor now contains only its domain-specific materialization:

```python
bindings = resolve_concrete_generic_bindings(
    cls,
    AccessorBase,
    MapperT=GenericBindingRequirement("_mapper_cls", Mapper),
)
if bindings is not None:
    cls._mapper_cls = bindings["MapperT"]
```

The helper intentionally does not assign the attribute itself. Most consumers
copy the resolved type directly, but `Mapper` turns a schema class into a shared
schema instance and `SubConfigKeyTransformer` turns `Literal["key"]` into the
string `"key"`. Keeping those transformations in their owning classes makes
the mutation visible and avoids a callback-heavy abstraction.

`Step` resolves both required types in one policy call, then performs its
domain-specific consistency check: the selected `StepContext` must declare the
same configuration model as the step.

## Intermediate and bare classes

These cases are intentionally different:

```python
class GenericView[MapperT: Mapper](AccessorBase[xr.Dataset, MapperT]):
    pass  # valid: MapperT is deliberately forwarded

class IncompleteView(GenericView):
    pass  # invalid: no type variable remains and no concrete type was supplied
```

The first class has `__type_params__`, so it is an intermediate generic class
and runtime materialization waits. The second is concrete from Python's point
of view; Tollan rejects it rather than silently using `Any` for runtime
behavior.

## Performance and lifetime

Resolution cost is proportional to the relevant generic inheritance graph and
is paid only in `__init_subclass__`. The materialized runtime attribute makes
all later access an ordinary class-attribute lookup.

There is no process-wide resolver cache. Python already prevents inheritance
cycles, the graphs are small, and a global cache would retain dynamically
created classes. Avoiding that lifetime risk is more important than memoizing a
one-time class-definition operation.

## Existing solutions considered

As of 2026-09-02, Python exposes the pieces but not a standard operation that
resolves an arbitrary class against an arbitrary generic ancestor.

| Option | What it provides | Why Tollan does not use it for this job |
| --- | --- | --- |
| Python standard library | Public `types.get_original_bases`, `typing.get_origin`, `typing.get_args`, `__type_params__`, and PEP 696 defaults | These are the correct building blocks, but there is no inheritance-wide substitution operation. A CPython typing maintainer has explicitly described richer runtime resolution as third-party-library territory. |
| `typing-inspection` | Actively maintained Pydantic project for inspecting individual annotations and qualifiers | It does not resolve an arbitrary generic ancestor through a user-defined inheritance graph. |
| `introspection.typing` | Broad helpers for generic aliases, arguments, parameters, and annotation conversion | It inspects individual type expressions but does not supply the required origin-aware inheritance resolver. |
| Pydantic generic models | Mature runtime specialization and caching for `BaseModel` subclasses | The useful substitution machinery is private and tied to Pydantic's generated model subclasses. `Mapper`, `AccessorBase`, and `Step` are ordinary classes. |
| `typing_inspect` | Experimental compatibility helpers for runtime typing objects | Its API is experimental and it does not solve the inheritance mapping. |
| `runtime-generics` | The closest match: decorated runtime generics, parent parameterization, runtime type checking | It changes generic subscription and class-method behavior, which is much broader than Tollan's class-definition inference. Its repository was archived in April 2025. |

The local resolver is therefore retained, but its scope is narrow: fixed-arity
`TypeVar`-based class hierarchies used by Tollan. `ParamSpec`, `TypeVarTuple`,
instance-level `__orig_class__`, and runtime checking of container contents are
not part of this contract.

Primary references:

- [Python `types.get_original_bases`](https://docs.python.org/3/library/types.html#types.get_original_bases)
- [Python runtime inspection helpers](https://docs.python.org/3/library/typing.html#introspection-helpers)
- [Python typing specification: generics](https://typing.python.org/en/latest/spec/generics.html)
- [PEP 695: type-parameter syntax](https://peps.python.org/pep-0695/)
- [PEP 696: type defaults](https://peps.python.org/pep-0696/)
- [`typing-inspection`](https://typing-inspection.pydantic.dev/latest/)
- [`introspection.typing`](https://aran-fey.github.io/introspection/build/html/typing.html)
- [Pydantic generic models](https://docs.pydantic.dev/latest/concepts/models/#generic-models)
- [`runtime-generics` archived repository](https://github.com/johnslavik/runtime_generics)
- [Python.org discussion of runtime `TypeVar` resolution](https://discuss.python.org/t/runtime-resolution-of-typevar/70388)

## Test contract

The low-level tests cover direct, indirect, reordered, nested, partial, and
defaulted bindings; unrelated generic bases; `Literal`; consistent and
conflicting diamonds; and invalid targets. The policy tests cover concrete
bound validation, intermediate deferral, bare-subclass rejection, and explicit
runtime-attribute rejection. Consumer tests exercise the actual accessor,
mapper, configuration, runtime-context, and pipeline declarations used by
Tolteca.

When extending the resolver, add a minimal inheritance graph to
`tests/utils/test_typing.py` first. Do not add a case merely because the
`typing` module can express it; add it when Tollan promises that construct as
part of this runtime contract.
