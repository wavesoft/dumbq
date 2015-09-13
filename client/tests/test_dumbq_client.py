# -*- coding: utf-8 -*-

# DumbQ 2.0 - A lightweight job scheduler
# Copyright (C) 2015-2016  Jorge Vicente Cantero, CERN

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

import os
import multiprocessing
import re
import tempfile
import shutil
import unittest

from uuid import UUID, uuid4

# If you run this locally, the parent folder should
# be added to the path. Otherwise these imports will fail
from dumbq_client import config
from dumbq_client import HardwareInfo, ConsoleLogger, DumbqSetup

from utils.utils import write_to_file


class BaseDumbqTest(unittest.TestCase):

    """Test class to check that Dumbq gets hardware info correctly."""

    def setUp(self):
        """Set up and replicate the production environment before testing."""
        self.config = config
        self.replicate_production_environment()

        # Only initialize when it is necessary
        self.hardware_info = None
        self.logger = None
        self.dumbq_setup = None
        self.project_hub = None
        self.project_manager = None

    def replicate_production_environment(self):
        tempfile.tempdir = tempfile.mkdtemp(dir="/tmp")

        _, self.uuid_fp = tempfile.mkstemp()
        self.config["uuid_file"] = self.uuid_fp
        _, self.cernvmconf_fp = tempfile.mkstemp()
        self.config["local_cernvm_config"] = self.cernvmconf_fp

        self.dumbq_dir = tempfile.mkdtemp()
        self.config["dumbq_dir"] = self.dumbq_dir
        self.www_dir = tempfile.mkdtemp()
        self.config["www_dir"] = self.www_dir

        _, self.test_logfile = tempfile.mkstemp()
        self.config["test_logfile"] = self.test_logfile

    def get_console_and_hw_info(self):
        return ConsoleLogger(), HardwareInfo(self.config)

    def get_dumbq_setup(self):
        logger, hw_info = self.get_console_and_hw_info()
        return DumbqSetup(hw_info, self.config, logger)

    def tearDown(self):
        """Destroy environment."""
        self.hardware_info = None
        self.logger = None
        self.dumbq_setup = None
        self.project_hub = None
        self.project_manager = None
        self.config = None

        # Remove tempfiles
        shutil.rmtree(tempfile.tempdir, ignore_errors=True)


class HardwareInfoTest(BaseDumbqTest):

    """Test class to check that Dumbq gets hardware info correctly."""

    def test_basic_hw_info(self):
        _, hardware_info = self.get_console_and_hw_info()
        assert hardware_info.number_cores == multiprocessing.cpu_count()
        assert isinstance(hardware_info.total_memory, int)
        assert isinstance(hardware_info.total_swap, int)
        assert isinstance(hardware_info.base_tty, int)
        assert isinstance(hardware_info.max_tty, int)

    def is_uuid(self, uuid_to_validate):
        try:
            return UUID(uuid_to_validate)
        except ValueError:
            return False

    def test_host_uuid_from_cernvm_config(self):
        new_uuid = str(uuid4())
        content = "CERNVM_UUID={0}".format(new_uuid)
        write_to_file(self.cernvmconf_fp, content)
        _, hardware_info = self.get_console_and_hw_info()
        assert hardware_info.host_uuid == new_uuid

    def test_host_uuid_is_generated_at_last(self):
        _, hardware_info = self.get_console_and_hw_info()
        assert self.is_uuid(hardware_info.host_uuid)

    def test_host_uuid_from_uuid_file(self):
        new_uuid = str(uuid4())
        write_to_file(self.uuid_fp, new_uuid)
        _, hardware_info = self.get_console_and_hw_info()
        assert new_uuid == hardware_info.host_uuid


class DumbqSetupTest(BaseDumbqTest):
    def test_folders_are_created(self):
        setup = self.get_dumbq_setup()
        setup.setup_config()
        setup.setup_dumbq_folders()
        setup.setup_public_www()
        folders = [self.www_dir]
        folders.extend(setup.dumbq_folders)
        print(folders)

        def folder_exists(f):
            assert os.path.exists(f)
        map(folder_exists, folders)

    def test_minimum_info_is_logged(self):
        setup = self.get_dumbq_setup()
        setup.setup_logger(testing=True)

        min_info = "(cpu=[0-9]+|mem=[0-9a-zA-Z]+|swap=[0-9a-zA-Z]+)"
        with open(self.test_logfile, "r") as lf:
            logger_output = " ".join(lf.readlines())
        # Find all because result may be in the same line
        print(logger_output)
        found = re.findall(min_info, logger_output)
        print(found)
        assert filter(lambda f: f.startswith("cpu"), found)
        assert filter(lambda f: f.startswith("mem"), found)
        assert filter(lambda f: f.startswith("swap"), found)


if __name__ == '__main__':
    unittest.main()
