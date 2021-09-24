#!/usr/bin/env python


from schema import Use
from ..dataclass_schema import add_schema
from dataclasses import dataclass, field
from ..fmt import pformat_yaml
from tollan.utils.log import get_logger


def test_dataclass_schema():

    @add_schema
    @dataclass
    class A(object):
        """The A class."""
        m: int
        n: int = field(default=1)

    @add_schema
    @dataclass
    class B(object):
        """The B class."""

        a_obj: A
        foo: str = field(
            default='bar',
            metadata={
                'description': 'Some uppercase value',
                'schema': Use(str.upper)}
            )

    @add_schema
    @dataclass
    class C(object):
        """The C class."""

        a_obj: A
        b_obj: B = field(
            default_factory=B.schema.default_factory(
                {'a_obj': {'m': 1, 'n': 10}, 'foo': 'baz'})
            )

    logger = get_logger()
    logger.debug(pformat_yaml(A.schema.json_schema('https://my.url.org/a')))
    logger.debug(pformat_yaml(B.schema.json_schema('https://my.url.org/b')))
    logger.debug(pformat_yaml(C.schema.json_schema('https://my.url.org/c')))
    logger.debug(A.schema.pformat())
    logger.debug(B.schema.pformat())
    logger.debug(C.schema.pformat())

    a_obj = A.from_dict({'m': 2})
    assert a_obj == A(m=2, n=1)

    b_obj = B.from_dict({'a_obj': {'m': 3}})
    assert b_obj == B(a_obj=A(m=3, n=1), foo='bar')

    b_obj = B.from_dict({'a_obj': {'m': 3}, 'foo': 'baz'})
    assert b_obj == B(a_obj=A(m=3, n=1), foo='BAZ')

    c_obj = C.from_dict({'a_obj': {'m': 4}})
    assert c_obj == C(
        a_obj=A(m=4, n=1),
        b_obj=B(a_obj=A(m=1, n=10), foo='BAZ'))
