import errno
import os
import json

from contextlib import contextmanager


def error_and_exit(error_message, logger):
    logger.error(error_message)
    exit(2)


@contextmanager
def ignored(*exceptions):
    try:
        yield
    except exceptions:
        pass

# TODO Create a loggable exception handler


def create_dir_if_nonexistent(dirpath, mode=0777):
    try:
        os.makedirs(dirpath)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def jsonify(**vars):
    return json.dumps(vars)
