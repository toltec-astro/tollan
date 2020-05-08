#! /usr/bin/env python

"""This module defines a set of helpers for defining database with
some column naming conventions."""

from sqlalchemy import (
        Table,
        Column, Integer, String, ForeignKey, DateTime)
from sqlalchemy.sql import expression
from sqlalchemy.ext.compiler import compiles
from sqlalchemy_utils import TimezoneType
import tzlocal
from ..sys import get_hostname


_excluded_from_all = set(globals().keys())


class utcnow(expression.FunctionElement):
    type = DateTime()


@compiles(utcnow, 'postgresql')
def pg_utcnow(element, compiler, **kw):
    return "TIMEZONE('utc', CURRENT_TIMESTAMP)"


@compiles(utcnow, 'mssql')
def ms_utcnow(element, compiler, **kw):
    return "GETUTCDATE()"


@compiles(utcnow)
def default_sql_utcnow(element, compiler, **kw):
    return 'CURRENT_TIMESTAMP'


def fk(other):
    return Column(
        f'{other}_pk', Integer,
        ForeignKey(
           f"{other}.pk", onupdate="cascade", ondelete="cascade"),
        nullable=False)


def pfk(other):
    return Column(
        f'{other}_pk', Integer,
        ForeignKey(
           f"{other}.pk", onupdate="cascade", ondelete="cascade"),
        primary_key=True)


def pk(**kwargs):
    return Column('pk', Integer, primary_key=True, **kwargs)


def label(**kwargs):
    return Column('label', String, **kwargs)


def created_at(**kwargs):
    return Column('created_at', DateTime, server_default=utcnow(), **kwargs)


def updated_at(**kwargs):
    return Column(
            'updated_at',
            DateTime, server_default=utcnow(), onupdate=utcnow())


def client_info(**kwargs):
    return fk('client_info')


def client_info_tbl(db):
    return Table(
            'client_info',
            db.metadata,
            pk(),
            Column(
                'hostname',
                String,
                default=get_hostname(),
                unique=True,
                sqlite_on_conflict_unique='REPLACE'
                ),
            Column(
                'tz',
                TimezoneType(backend='pytz'),
                default=tzlocal.get_localzone()
                ),
            created_at(),
            updated_at(),
            )


__all__ = list(set(globals().keys()).difference(_excluded_from_all))
