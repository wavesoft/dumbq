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
import sys
import subprocess

from contextlib import contextmanager

DEVNULL = os.open(os.devnull, os.O_RDWR)
default_write_error = "Problem when writing to {0}"
default_read_error = "Problem when reading from {0}"


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


@contextmanager
def ignored(*exceptions):
    """Ignore certain type of exceptions."""
    try:
        yield
    except exceptions:
        pass


@contextmanager
def logged(f_logger, message, *exceptions):
    """Log a message when a certain type of exceptions occur."""
    try:
        yield
    except exceptions:
        f_logger(message)


def write_to_file(filepath, content):
    """Write to a file."""
    with open(filepath, "w") as f:
        f.write(content)


def safe_write_to_file(filepath, content, f_logger, error_feedback=None):
    """Write to a file logging any exception."""
    feedback = error_feedback or default_write_error.format(filepath)
    with logged(f_logger, feedback, (EnvironmentError,)):
        return write_to_file(filepath, content)


def read_from_file(filepath, lines=False):
    """Read from a file raw content or lines."""
    with open(filepath, "r") as f:
        return f.readlines() if lines else f.read()


def safe_read_from_file(filepath, f_logger, error_feedback=None, lines=False):
    """Read from a file raw content or lines logging any exception."""
    feedback = error_feedback or default_read_error.format(filepath)
    with logged(f_logger, feedback, (IOError,)):
        return read_from_file(filepath, lines)


def error_and_exit(error_message, logger):
    """Log error and exit."""
    logger.error(error_message)
    sys.exit(2)


def create_dir_if_nonexistent(dirpath, mode=0777):
    """Create a directory if it does not exist, otherwise ignore."""
    try:
        os.makedirs(dirpath)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def jsonify(**vars):
    """Idiom to convert to json."""
    return json.dumps(vars)
