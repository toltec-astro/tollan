#! /usr/bin/env python


"""This module provides functionalities from ``STILTS``."""


import os
from ..log import get_logger, logit
from . import get_wraps_dir
import shutil
import stat
import subprocess
import re
import tempfile
from contextlib import ExitStack
from astropy.table import Table


def ensure_stilts():
    logger = get_logger()
    extern_dir = get_wraps_dir()
    which_path = f"{extern_dir.resolve().as_posix()}:{os.getenv('PATH')}"
    # which_path = f"{extern_dir.resolve().as_posix()}"
    # logger.debug(f"extern search paths: {which_path}")
    stilts_cmd = shutil.which("stilts", path=which_path)
    if stilts_cmd is None:
        logger.warning("unable to find stilts, download from internet")
        with logit(logger.debug, "setup stilts"):
            # retrieve stilts
            from astropy.utils.data import download_file
            stilts_jar_tmp = download_file(
                    "http://www.star.bris.ac.uk/%7Embt/stilts/stilts.jar",
                    cache=True)
            stilts_jar = extern_dir.joinpath('stilts.jar')
            shutil.copyfile(stilts_jar_tmp, stilts_jar)
            stilts_cmd = extern_dir.joinpath('stilts')
            with open(stilts_cmd, 'w') as fo:
                fo.write("""#!/bin/sh
java -Xmx4000M -classpath "{0}:$CLASSPATH" uk.ac.starlink.ttools.Stilts "$@"
""".format(stilts_jar.resolve()))
            os.chmod(
                    stilts_cmd,
                    os.stat(stilts_cmd).st_mode | stat.S_IEXEC)
    # verify that stilts works
    try:
        output = subprocess.check_output(
                (stilts_cmd, '-version'),
                stderr=subprocess.STDOUT
                ).decode().strip('\n')
    except Exception as e:
        raise RuntimeError(f"error when run stilts {stilts_cmd}: {e}")
    else:
        logger.debug(f"\n\n{output}\n")
    return stilts_cmd


def run_stilts(cmd, *tbls):
    logger = get_logger()
    with ExitStack() as es:
        for i, c in enumerate(cmd):
            s = re.match(r'(.+)=\$(\d+)', c)
            if s is not None:
                a = int(s.group(2)) - 1
                t = tbls[a]
                if not isinstance(t, str):
                    f = es.enter_context(
                            tempfile.NamedTemporaryFile())
                    logger.debug(f"write table to {f.name}")
                    t.write(
                            f.name,
                            format='ascii.commented_header', overwrite=True)
                    t = f.name
                cmd[i] = f"{s.group(1)}={t}"
        logger.debug("run stilts: {}".format(' '.join(cmd)))
        exitcode = subprocess.check_call(cmd)
    return exitcode


def stilts_match1d(
        tbl1, tbl2, colname, radius,
        stilts_cmd=None,
        extra_args=None
        ):
    if stilts_cmd is None:
        stilts_cmd = ensure_stilts()
    cmd = [
        stilts_cmd,
        "tmatch2",
        "in1=$1", "ifmt1=ascii",
        "in2=$2", "ifmt2=ascii",
        "matcher=1d", f"params={radius}", f"values1='{colname}'",
        f"values2='{colname}'",
        # "action=keep1",
        "out=$3", "ofmt=ascii"]
    if extra_args is not None:
        cmd.extend([a for a in extra_args])

    f = tempfile.NamedTemporaryFile()

    try:
        run_stilts(cmd, tbl1, tbl2, f.name)
    except Exception as e:
        raise RuntimeError(f"failed run {' '.join(cmd)}: {e}")
    else:
        tbl = Table.read(f.name, format='ascii.commented_header')
        return tbl
