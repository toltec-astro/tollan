import tempfile
from pathlib import Path

import pytest

from tollan.config.directory_preset import (
    DirectoryPresetBase,
    PathItem,
    PathValidationError,
    validate_path,
)
from tollan.utils.general import ensure_abspath
from tollan.utils.sys import touch_file


def test_validate_path():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        test_dir = tmp.joinpath("test_dir")
        test_dir_validated = validate_path(
            test_dir,
            type_required="dir",
            create=True,
            clean_create_only=True,
            backup=True,
            name="test_dir",
            on_create=lambda p: touch_file(p.joinpath("test_file")),
        )
        assert test_dir_validated == test_dir
        assert test_dir_validated.exists()
        assert test_dir_validated.is_dir()
        contents = list(test_dir_validated.glob("*"))
        assert len(contents) == 1
        assert contents[0].name == "test_file"
        # now recreate the dir again with creato to false
        # this should be no-op
        test_dir_validated = validate_path(
            test_dir,
            type_required="dir",
            create=False,
            clean_create_only=True,
            backup=True,
            name="test_dir",
            on_create=lambda p: touch_file(p.joinpath("test_file")),
        )
        assert test_dir_validated == test_dir
        assert test_dir_validated.exists()
        assert test_dir_validated.is_dir()
        contents = list(test_dir_validated.glob("*"))
        assert len(contents) == 1
        assert contents[0].name == "test_file"

        # now recreate the dir again with create to true and backup to false
        # this should be error because of the path is not clean
        with pytest.raises(PathValidationError, match="exists or is not empty"):
            test_dir_validated = validate_path(
                test_dir,
                type_required="dir",
                create=True,
                clean_create_only=True,
                backup=False,
                name="test_dir",
                on_create=lambda p: touch_file(p.joinpath("test_file")),
            )
        # now recreate the dir again with create to true and allow non-clean creation
        # with backup off
        test_dir_validated = validate_path(
            test_dir,
            type_required="dir",
            create=True,
            clean_create_only=False,
            backup=False,
            name="test_dir",
            on_create=lambda p: touch_file(p.joinpath("test_file")),
        )
        assert test_dir_validated == test_dir
        assert test_dir_validated.exists()
        assert test_dir_validated.is_dir()
        contents = list(test_dir_validated.glob("*"))
        assert len(contents) == 1
        assert contents[0].name == "test_file"
        backups = list(tmp.glob("*.bak"))
        assert len(backups) == 0

        # now recreate the dir again with create to true and backup for a clean create
        test_dir_validated = validate_path(
            test_dir,
            type_required="dir",
            create=True,
            backup=True,
            name="test_dir",
            on_create=lambda p: touch_file(p.joinpath("test_file")),
        )
        assert test_dir_validated == test_dir
        assert test_dir_validated.exists()
        assert test_dir_validated.is_dir()
        contents = list(test_dir_validated.glob("*"))
        assert len(contents) == 1
        assert contents[0].name == "test_file"
        backups = list(tmp.glob("*.bak"))
        assert len(backups) == 1
        assert backups[0].name.startswith("test_dir.")
        assert list(backups[0].glob("*"))[0].name == "test_file"


def test_dir_preset():
    class Preset(DirectoryPresetBase):
        class Config:
            content_path_items = [
                PathItem(name="test_dir", path_name="test_dir", path_type="dir"),
                PathItem(name="test_file", path_name="test_file", path_type="file"),
                PathItem(
                    name="test_config_files", path_name="**/*.yaml", path_type="glob"
                ),
            ]

        def __init__(self, rootpath, **kwargs):
            super().__init__(rootpath)
            self.validate(self.rootpath, **kwargs)

    with tempfile.TemporaryDirectory() as tmp:
        test_rootpath = ensure_abspath(Path(tmp).joinpath("test_rootpath"))
        with pytest.raises(PathValidationError, match="missing path"):
            dp = Preset(test_rootpath, create=False)
        dp = Preset(test_rootpath, create=True)
        assert dp.rootpath == test_rootpath and dp.rootpath.exists()
        assert (
            dp.test_dir == test_rootpath.joinpath("test_dir") and dp.test_dir.exists()
        )
        assert (
            dp.test_file == test_rootpath.joinpath("test_file")
            and dp.test_file.exists()
        )
        assert list(dp.test_config_files) == []
        # validate again with create = False,
        # but this time we add some yaml config files
        touch_file(dp.test_dir / "a.yaml")
        touch_file(dp.rootpath / "b.yaml")
        dp = Preset(test_rootpath, create=False)
        assert dp.rootpath == test_rootpath and dp.rootpath.exists()
        assert (
            dp.test_dir == test_rootpath.joinpath("test_dir") and dp.test_dir.exists()
        )
        assert (
            dp.test_file == test_rootpath.joinpath("test_file")
            and dp.test_file.exists()
        )
        assert set(dp.test_config_files) == {
            dp.test_dir / "a.yaml",
            dp.rootpath / "b.yaml",
        }

        # validate again with create=True, and backup=False, which errors because the directory is dirty
        with pytest.raises(
            PathValidationError, match="invalid path: .+ exists or is not empty"
        ):
            dp = Preset(test_rootpath, create=True, backup=False)

        # this works because we allow create in dirty state
        dp = Preset(test_rootpath, create=True, clean_create_only=False, backup=False)
        assert dp.rootpath == test_rootpath and dp.rootpath.exists()
        assert (
            dp.test_dir == test_rootpath.joinpath("test_dir") and dp.test_dir.exists()
        )
        assert (
            dp.test_file == test_rootpath.joinpath("test_file")
            and dp.test_file.exists()
        )
        assert set(dp.test_config_files) == {
            dp.test_dir / "a.yaml",
            dp.rootpath / "b.yaml",
        }
        # check this is the only directory and no backup is created
        backups = list(test_rootpath.parent.glob(test_rootpath.name + "*"))
        assert len(backups) == 1

        # now create with backup, it works because a backup workdir is created
        dp = Preset(test_rootpath, create=True, backup=True, inplace_backup=False)
        assert dp.rootpath == test_rootpath and dp.rootpath.exists()
        assert (
            dp.test_dir == test_rootpath.joinpath("test_dir") and dp.test_dir.exists()
        )
        assert (
            dp.test_file == test_rootpath.joinpath("test_file")
            and dp.test_file.exists()
        )
        # files are now in the backup folder
        assert set(dp.test_config_files) == set()
        # check this is the only directory and no backup is created
        backups = list(test_rootpath.parent.glob(test_rootpath.name + "*.bak"))
        assert len(backups) == 1
        assert set(backups[0].glob("**/*.yaml")) == {
            backups[0] / "test_dir" / "a.yaml",
            backups[0] / "b.yaml",
        }

        # now check the inplace backup
        # to check backup glob pattern files, we create two files:
        touch_file(dp.test_dir / "a.yaml")
        touch_file(dp.rootpath / "b.yaml")
        # import subprocess
        #
        # print(subprocess.check_output(["tree", str(dp.rootpath)]).decode())
        dp = Preset(test_rootpath, create=True, backup=True, inplace_backup=True)
        #
        # print(subprocess.check_output(["tree", str(dp.rootpath)]).decode())
        assert dp.rootpath == test_rootpath and dp.rootpath.exists()
        assert (
            dp.test_dir == test_rootpath.joinpath("test_dir") and dp.test_dir.exists()
        )
        assert (
            dp.test_file == test_rootpath.joinpath("test_file")
            and dp.test_file.exists()
        )
        # files are now in the backup folder
        assert set(dp.test_config_files) == set()
        # check this is the only directory and no backup is created
        backups = list(test_rootpath.glob(test_rootpath.name + "*.bak"))
        assert len(backups) == 1
        assert set(backups[0].glob("**/*.yaml")) == {
            backups[0] / "test_dir" / "a.yaml",
            backups[0] / "b.yaml",
        }
