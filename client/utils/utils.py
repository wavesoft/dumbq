import errno
import os

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


def create_dir_if_nonexistent(dirpath, mode=0777):
    try:
        os.makedirs(dirpath)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise
