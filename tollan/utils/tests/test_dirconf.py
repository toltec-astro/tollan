#! /usr/bin/env python

import tempfile
import yaml
from pathlib import Path
from schema import Optional
import pytest
from ..dirconf import DirConfMixin, DirConfError
from ..sys import touch_file


class SimpleDirConf(DirConfMixin):

    _contents = {
            'logdir': {
                'path': 'log',
                'type': 'dir',
                'backup_enabled': False,
                },
            'baseconf': {
                'path': '00_a.yaml',
                'type': 'file',
                'backup_enabled': True
                },
            }

    extend_config_schema = {
            Optional('default_key', default='default_value'): str,
            object: object
            }

    def __init__(self, rootpath, **kwargs):
        self.rootpath = self.populate_dir(rootpath, **kwargs)

    def get_config(self):
        return self.collect_config_from_files(self.collect_config_files())


def test_dirconf_mixin():
    # collect config
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
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
        DirConfMixin.write_config_to_yaml(
                cfg, tmp / 'out.yaml', overwrite=True)
        with open(tmp / 'out.yaml', 'r') as fo:
            cfg_out = yaml.safe_load(fo)
        assert cfg_out == cfg


def test_dirconf_simple():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        dc = SimpleDirConf(tmp, create=True)
        assert dc.rootpath == tmp
        assert dc.to_dict() == {
                'rootpath': tmp,
                'logdir': tmp / 'log',
                'baseconf': tmp / '00_a.yaml',
                }
        assert all(getattr(dc, f).exists() for f in ['logdir', 'baseconf'])
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
        touch_file(tmp / "not_a_config.yaml")
        assert [f.name for f in dc.collect_config_files()] == \
            ['00_a.yaml', '10_b.yaml']

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
                create=False, force=False, overwrite=False, dry_run=False)
        # with pytest.raises(
        #         DirConfError, match='not empty'):
        # all items are present, not action
        assert SimpleDirConf(
            dc.rootpath,
            create=False, force=True, overwrite=False, dry_run=False)
        dc.logdir.rename(dc.logdir.with_name('log.removed'))
        # missing logdir
        with pytest.raises(
                DirConfError, match='Set create=True to create'):
            assert SimpleDirConf(
                dc.rootpath,
                create=False, force=True, overwrite=False, dry_run=False)

        # create a new logdir
        assert SimpleDirConf(
            dc.rootpath,
            create=True, force=True, overwrite=False, dry_run=False)
        # backup of baseconf should be present
        assert len(list(dc.rootpath.glob('00_a.yaml.*'))) == 1
        # create with overwrite
        next(iter(dc.rootpath.glob('00_a.yaml.*'))).rename(tmp / 'a_removed')
        assert SimpleDirConf(
            dc.rootpath,
            create=True, force=True, overwrite=False, dry_run=False)
        # no new backup is created
        assert len(list(dc.rootpath.glob('00_a.yaml.*'))) == 0
