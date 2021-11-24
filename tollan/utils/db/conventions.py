#! /usr/bin/env python

"""This module defines a set of helpers for defining database with
some column naming conventions."""

from sqlalchemy import (
        Column, Integer, String, ForeignKey, DateTime, Text)
from sqlalchemy.sql import expression
from sqlalchemy.ext.compiler import compiles
from sqlalchemy_utils import TimezoneType
import tzlocal
from ..sys import get_hostname
# from sqlalchemy.sql.expression import Insert


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


# @compiles(Insert, 'postgresql')
# def ignore_duplicates(insert, compiler, **kw):
#     s = compiler.visit_insert(insert, **kw)
#     ignore = insert.kwargs.get('postgresql_ignore_duplicates', False)
#     return s if not ignore else s + ' ON CONFLICT DO NOTHING'
# Insert.argument_for('postgresql', 'ignore_duplicates', None)


def fk(other, name=None, **kwargs):
    if name is None:
        name = f'{other}_pk'
    kwargs.setdefault('comment', f'The {other} primary key.')
    kwargs.setdefault('nullable', False)
    return Column(
        name, Integer,
        ForeignKey(
           f"{other}.pk", onupdate="cascade", ondelete="cascade",
           ),
        **kwargs
        )


def pfk(other, name=None, **kwargs):
    if name is None:
        name = f'{other}_pk'
    kwargs.setdefault('comment', f'The shared primary key from {other}.')
    return Column(
        name, Integer,
        ForeignKey(
           f"{other}.pk", onupdate="cascade", ondelete="cascade",
           ),
        primary_key=True, **kwargs)


def pk(**kwargs):
    kwargs.setdefault('comment', 'The primary key.')
    return Column(
            'pk', Integer, primary_key=True,
            **kwargs)


def name(**kwargs):
    return Column(
            'name', String(128),
            comment='The name.',
            **kwargs)


def label(**kwargs):
    return Column(
            'label', String(128),
            unique=True,
            sqlite_on_conflict_unique='REPLACE',
            comment='The short descriptive label.',
            **kwargs)


def desc(**kwargs):
    return Column(
            'desc', Text,
            comment='The long description.',
            **kwargs)


def created_at(**kwargs):
    return Column(
            'created_at', DateTime,
            server_default=utcnow(),
            comment='The datetime of creation.',
            **kwargs)


def updated_at(**kwargs):
    return Column(
            'updated_at',
            DateTime, server_default=utcnow(),
            comment='The datetime of last modification.',
            onupdate=utcnow())


# Some useful utility tables
CLIENT_INFO_TABLE_NAME = 'client_info'


def client_info_table():
    t = {
        'name': CLIENT_INFO_TABLE_NAME,
        'desc': 'The client info.',
        'columns': [
            pk(),
            Column(
                'hostname',
                String(128),
                default=get_hostname(),
                unique=True,
                sqlite_on_conflict_unique='REPLACE',
                comment='The client hostname.'
                ),
            Column(
                'tz',
                TimezoneType(backend='pytz'),
                default=tzlocal.get_localzone_name(),
                comment='The client time zone.'
                ),
            created_at(),
            updated_at(),
            ]
        }
    return t


def client_info_fk(**kwargs):
    return fk(CLIENT_INFO_TABLE_NAME)


def client_info_model(Base):

    class ClientInfo(Base):

        __tablename__ = CLIENT_INFO_TABLE_NAME

        def __repr__(self):
            return f'{self.__class__.__name__}(hostname={self.hostname})'

    return ClientInfo


TABLE_INFO_TABLE_NAME = '_table_info'


def table_info_table():
    t = {
        'name': TABLE_INFO_TABLE_NAME,
        'desc': 'The table info.',
        'columns': [
            pk(),
            name(unique=True),
            desc(),
            ],
        'data': []
        }
    return t


__all__ = list(set(globals().keys()).difference(_excluded_from_all))
