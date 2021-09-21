#! /usr/bin/env python

import tempfile
import yaml
from pathlib import Path
from schema import Optional
import pytest
from .. import odict_from_list
from ..dirconf import (
    DirConfYamlDumper, DirConfPathType, DirConfPath, DirConfMixin,
    DirConfError)
from ..sys import touch_file
import astropy.units as u


def test_dirconf_yaml_dumper():
    d = {
        'a': 1.0 << u.km,
        'b': Path('a/b')
        }
    s = yaml.dump(d, Dumper=DirConfYamlDumper)
    assert 'a: 1.0 km' in s


def test_dirconf_paths():

    c = odict_from_list([
            DirConfPath(
                label='some_dir',
                path_name='a_dir',
                path_type=DirConfPathType.DIR,
            ),
            DirConfPath(
                label='some_file',
                path_name='b_file',
                path_type=DirConfPathType.FILE,
                backup_enabled=True
            ),
        ], key=lambda p: p.label)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()

        d = c['some_dir']
        assert not d.backup_enabled  # defult is not backup
        assert d.resolve_path(Path('.')) == Path(d.path_name)
        assert d.resolve_path(tmp) == tmp.joinpath(d.path_name)
        # create for the first time
        p0 = d.create(tmp, disable_backup=False, dry_run=True)  # not created
        assert not p0.exists()
        p0 = d.create(tmp, disable_backup=False, dry_run=False)
        assert p0 == d.resolve_path(tmp)
        assert p0.exists()
        # create for the second time does not create backup
        p1 = d.create(tmp, disable_backup=False, dry_run=False)
        assert p1 == p0
        assert len(list(tmp.glob(f'{d.path_name}.*'))) == 0

        f = c['some_file']
        assert f.backup_enabled  # set
        assert f.resolve_path(Path('.')) == Path(f.path_name)
        assert f.resolve_path(tmp) == tmp.joinpath(f.path_name)
        # create for the first time
        p0 = f.create(tmp, disable_backup=False, dry_run=True)  # not created
        assert not p0.exists()
        p0 = f.create(tmp, disable_backup=False, dry_run=False)
        assert p0 == f.resolve_path(tmp)
        assert p0.exists()
        # create for the second time without disable_backup create backup
        p1 = f.create(tmp, disable_backup=False, dry_run=False)
        assert p1.exists()
        assert len(list(tmp.glob(f'{f.path_name}.*'))) == 1
        # create for the third time with disable_backup not create backup
        p2 = f.create(tmp, disable_backup=True, dry_run=False)
        assert p2.exists()
        assert len(list(tmp.glob(f'{f.path_name}.*'))) == 1
        assert f.rename_as_backup(tmp) == list(tmp.glob(f'{f.path_name}.*'))[0]


class SimpleDirConf(DirConfMixin):

    _contents = odict_from_list([
        DirConfPath(
            label='logdir',
            path_name='log',
            path_type=DirConfPathType.DIR,
            ),
        DirConfPath(
            label='baseconf',
            path_name='00_baseconf.yaml',
            path_type=DirConfPathType.FILE,
            backup_enabled=True,
            ),
        ], key=lambda a: a.label)

    extend_config_schema = {
            Optional('default_key', default='default_value'): str,
            Optional(str): object
            }

    def __init__(self, rootpath, **kwargs):
        self.rootpath = self.populate_dir(rootpath, **kwargs)

    def get_config(self):
        return self.collect_config_from_files(self.collect_config_files())


def test_dirconf_mixin():
    # collect config
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        with open(tmp / '00_a.yaml', 'w') as fa, \
                open(tmp / '10_b.yaml', 'w') as fb:
            fa.write('''
---
a: 1
b:
  c: 2
''')
            fb.write('''
---
b:
  c: 1
d: 'test'
''')
        cfg = DirConfMixin.collect_config_from_files(
                [
                    tmp / '00_a.yaml',
                    ],
                validate=False
                )
        assert cfg == {
                'a': 1,
                'b': {
                    'c': 2
                    }
                }
        cfg = DirConfMixin.collect_config_from_files(
                [
                    tmp / '00_a.yaml',
                    tmp / '10_b.yaml',
                    ],
                validate=False
                )
        assert cfg == {
                'a': 1,
                'b': {
                    'c': 1
                    },
                'd': 'test'
                }
        # write to yaml and roundtrip
        with open(tmp / 'out.yaml', 'w') as fo:
            DirConfMixin.yaml_dump(cfg, fo)
        with open(tmp / 'out.yaml', 'r') as fo:
            cfg_out = DirConfMixin.yaml_load(fo)
        assert cfg_out == cfg


def test_dirconf_simple():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp).resolve()
        dc = SimpleDirConf(tmp, create=True)
        assert dc.rootpath == tmp
        assert dc.get_content_paths() == {
                'rootpath': tmp,
                'logdir': tmp / 'log',
                'baseconf': tmp / '00_baseconf.yaml',
                }
        assert all(getattr(dc, f).exists() for f in ['logdir', 'baseconf'])
        with open(tmp / '00_baseconf.yaml', 'w') as fa, \
                open(tmp / '10_b.yaml', 'w') as fb:
            fa.write('''
---
a: 1
b:
  c: 2
''')
            fb.write('''
---
b:
  c: 1
d: 'test'
''')
        touch_file(tmp / "not_a_config.yaml")
        assert [f.name for f in dc.collect_config_files()] == \
            ['00_baseconf.yaml', '10_b.yaml']

        assert dc.get_config() == {
                'a': 1,
                'b': {'c': 1},
                'd': 'test',
                'default_key': 'default_value'
                }
        # populate one more time
        with pytest.raises(
                DirConfError, match='not empty'):
            dc = SimpleDirConf(
                dc.rootpath,
                create=False, force=False, disable_backup=False, dry_run=False)
        # with pytest.raises(
        #         DirConfError, match='not empty'):
        # all items are present, not action
        assert SimpleDirConf(
            dc.rootpath,
            create=False, force=True, disable_backup=False, dry_run=False)
        dc.logdir.rename(dc.logdir.with_name('log.removed'))
        # missing logdir
        with pytest.raises(
                DirConfError, match='Set create=True to create'):
            assert SimpleDirConf(
                dc.rootpath,
                create=False, force=True, disable_backup=False, dry_run=False)

        # create a new logdir
        assert SimpleDirConf(
            dc.rootpath,
            create=True, force=True, disable_backup=False, dry_run=False)
        # backup of baseconf should be present
        assert len(list(dc.rootpath.glob('00_baseconf.yaml.*'))) == 1
        # create with disable_backup
        next(iter(dc.rootpath.glob('00_baseconf.yaml.*'))).rename(
            tmp / 'baseconf_removed')
        assert SimpleDirConf(
            dc.rootpath,
            create=True, force=True, disable_backup=True, dry_run=False)
        # no new backup is created
        assert len(list(dc.rootpath.glob('00_baseconf.yaml.*'))) == 0
