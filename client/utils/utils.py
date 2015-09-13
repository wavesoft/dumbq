# -*- coding: utf-8 -*-

# DumbQ 2.0 - A lightweight job scheduler
# Copyright (C) 2015-2016 Jorge Vicente Cantero, CERN

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA

import errno
import os
import json

from contextlib import contextmanager

DEVNULL = os.open(os.devnull, os.O_RDWR)

import subprocess


def check_output(*popenargs, **kwargs):
    r"""Run command with arguments and return its output as a byte string.
    Backported from Python 2.7 as it's implemented as pure python on stdlib.
    >>> check_output(['/usr/bin/python', '--version'])
    Python 2.6.2
    """
    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate()
    retcode = process.poll()
    if retcode:
        cmd = kwargs.get("args")
        if cmd is None:
            cmd = popenargs[0]
        error = subprocess.CalledProcessError(retcode, cmd)
        error.output = output
        raise error
    return output


def write_to_file(filepath, content):
    with open(filepath, "w") as f:
        f.write(content)


def read_from_file(filepath):
    with open(filepath, "r") as f:
        return f.read()


@contextmanager
def post_empty(filepath):
    try:
        yield
    except Exception as e:
        raise e
    else:
        with ignored(EnvironmentError):
            write_to_file(filepath, "")


def error_and_exit(error_message, logger):
    logger.error(error_message)
    exit(2)


@contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass


@contextmanager
def logged(logger, message, *exceptions):
    try:
        yield
    except exceptions:
        logger.warning(message)


def create_dir_if_nonexistent(dirpath, mode=0777):
    try:
        os.makedirs(dirpath)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def jsonify(**vars):
    return json.dumps(vars)
