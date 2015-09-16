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

"""Test suite for all the components in DumbQ."""

import multiprocessing
import os
import re
import shutil
import tempfile
import unittest

from string import lstrip
from uuid import UUID, uuid4

# Add the parent folder to the path if run locally, otherwise imports fail
from dumbq_client import config, feedback
from dumbq_client import HardwareInfo, ConsoleLogger, DumbqSetup
from dumbq_client import ProjectHub, ProjectManager

from utils.utils import write_to_file, read_from_file
from utils.test_utils import safe_repr


class BaseDumbqTest(unittest.TestCase):

    """Base test class that initializes and destroys DumbQ environment."""

    def setUp(self):
        """Set up and replicate the production environment before testing."""
        self.config = config
        self.feedback = feedback

        # Just declare, lazy initialization
        self.hardware_info = None
        self.logger = None
        self.dumbq_setup = None
        self.project_hub = None
        self.project_manager = None

        self.replicate_production_environment()

    def replicate_production_environment(self):
        """Mock the environment with temp files, solving dependencies."""
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

        self.setup_config_files()

        _, self.shared = tempfile.mkstemp()
        _, self.guest = tempfile.mkstemp()
        self.config["shared_meta_file"] = self.shared + "=" + self.guest

    def setup_config_files(self):
        """Define the configuration files to be tested afterwards."""
        self.valid_config_content = "\n".join((
            "test1:80:sft.cern.ch:sft.cern.ch/lcg/experimental/bootstrap.sh",
            "test2:20:sft.cern.ch:sft.cern.ch/lcg/experimental/bootstrap2.sh",
        ))

        self.invalid_config_content = "\n".join((
            "test1:05:sft.cern.ch:../malign/script.sh",
            "test2::sft.cern.ch:sft.cern.ch/lcg/experimental/bootstrap.sh",
            "test3:80::",
            ":80:sft.cern.ch:",
            ":::",
        ))

        self.incomplete_config_content = "\n".join((
            "test1:45:sft.cern.ch:sft.cern.ch/lcg/init-bootstrap.sh",
            "test2:45:sft.cern.ch:sft.cern.ch/lcg/init-bootstrap2.sh",
        ))

        self.pref_config_content = "\n".join((
            "test1:90",
            "test2:10",
        ))

        self.pref_config_content2 = "\n".join((
            "test1:30",
            "test2:40",
            "*:50",
        ))

        _, self.config_source = tempfile.mkstemp()
        self.config["config_source"] = self.config_source

    def init_console_and_hw_info(self):
        """Init logger and hardware info with its dependencies."""
        self.logger = ConsoleLogger()
        self.hardware_info = HardwareInfo(
            self.config, self.feedback, self.logger
        )

    def init_dumbq_setup(self):
        """Init dumbq setup with its dependencies."""
        self.init_console_and_hw_info()
        self.dumbq_setup = DumbqSetup(
            self.hardware_info, self.config, self.logger
        )

    def init_project_hub(self, config_content=None, pref_content=None):
        """Init project hub with its dependencies."""
        self.init_dumbq_setup()
        self.dumbq_setup.setup_config()
        self.dumbq_setup.setup_dumbq_folders()
        self.dumbq_setup.setup_logger(testing=True)
        self.dumbq_setup.setup_public_www()

        config_content = config_content or self.valid_config_content
        pref_content = pref_content or ""
        self.pref_config_source = config["preference_config_source"]
        write_to_file(self.config_source, config_content)
        write_to_file(self.pref_config_source, pref_content)

        self.project_hub = ProjectHub(
            self.config, self.feedback, self.logger
        )

    def init_project_manager(self):
        """Init project manager with its dependencies."""
        self.init_project_hub()
        self.project_hub.fetch_config_file()
        self.project_hub.fetch_preference_file()
        self.project_hub.parse_shared_and_guest_metadata_file()

        self.project_manager = ProjectManager(
            self.project_hub, self.hardware_info, self.config, self.logger
        )

    def tearDown(self):
        """Destroy environment and free used resources."""
        self.hardware_info = None
        self.logger = None
        self.dumbq_setup = None
        self.project_hub = None
        self.project_manager = None
        self.config = None

        # Remove tempfiles
        shutil.rmtree(tempfile.tempdir, ignore_errors=True)

    ############################################################
    # Monkey patch from unittest 2.7 advanced assert functions #
    ############################################################

    def assertIn(self, member, container, msg=None):
        """Just like self.assertTrue(a in b), with a nicer default message."""
        if member not in container:
            standardMsg = '%s not found in %s' % (safe_repr(member),
                                                  safe_repr(container))
            self.fail(self._formatMessage(msg, standardMsg))

    def assertIsInstance(self, obj, cls, msg=None):
        """Same as self.assertTrue(isinstance(obj, cls)), with a nicer
        default message."""
        if not isinstance(obj, cls):
            standardMsg = '%s is not an instance of %r' % (safe_repr(obj), cls)
            self.fail(self._formatMessage(msg, standardMsg))


class HardwareInfoTest(BaseDumbqTest):

    """Test suite for HardwareInfo."""

    def test_basic_hw_info(self):
        """Test that HardwareInfo gets correct values."""
        self.init_console_and_hw_info()
        cpu_count = multiprocessing.cpu_count()
        self.assertEqual(self.hardware_info.number_cores, cpu_count)
        self.assertIsInstance(self.hardware_info.total_memory, int)
        self.assertIsInstance(self.hardware_info.total_swap, int)
        self.assertIsInstance(self.hardware_info.base_tty, int)
        self.assertIsInstance(self.hardware_info.max_tty, int)

    def is_uuid(self, uuid_to_validate):
        """Check if a string is a correct UUID."""
        try:
            return UUID(uuid_to_validate)
        except ValueError:
            return False

    def test_host_uuid_from_cernvm_config(self):
        """Test host uuid is from the cernvm file."""
        new_uuid = str(uuid4())
        content = "CERNVM_UUID={0}".format(new_uuid)
        write_to_file(self.cernvmconf_fp, content)
        self.init_console_and_hw_info()
        self.assertEqual(self.hardware_info.host_uuid, new_uuid)

    def test_host_uuid_from_uuid_file(self):
        """Test host uuid is from the uuid file, if cernvm not present."""
        new_uuid = str(uuid4())
        write_to_file(self.uuid_fp, new_uuid)
        self.init_console_and_hw_info()
        self.assertEqual(new_uuid, self.hardware_info.host_uuid)

    def test_host_uuid_is_generated_at_last(self):
        """Test host uuid is generated."""
        self.init_console_and_hw_info()
        gen_uuid = self.hardware_info.host_uuid
        self.assertTrue(self.is_uuid(gen_uuid))
        self.assertEqual(gen_uuid, read_from_file(self.uuid_fp))


class DumbqSetupTest(BaseDumbqTest):

    """Test suite for DumbqSetup."""

    def test_folders_are_created(self):
        """Test that necessary folders exist at init."""
        self.init_dumbq_setup()
        self.dumbq_setup.setup_config()
        self.dumbq_setup.setup_dumbq_folders()
        self.dumbq_setup.setup_public_www()

        folders = [self.www_dir]
        folders.extend(self.dumbq_setup.dumbq_folders)
        existing_folders = filter(lambda f: os.path.exists(f), folders)
        for folder in folders:
            self.assertIn(folder, existing_folders)

    def test_minimum_info_is_logged(self):
        """Test that, at least, certain hardware info is printed at init."""
        self.init_dumbq_setup()
        self.dumbq_setup.setup_logger(testing=True)

        displayed_info = "(cpu|mem|swap)=\w"
        logger_output = read_from_file(self.test_logfile)
        matches = re.findall(displayed_info, logger_output)

        self.assertIn("cpu", matches)
        self.assertIn("mem", matches)
        self.assertIn("swap", matches)


class ProjectHubTest(BaseDumbqTest):

    """Test suite for the ProjectHub."""

    def test_valid_config_file(self):
        """Test that a valid config file is correctly parsed."""
        self.init_project_hub()
        self.project_hub.fetch_config_file()
        self.assertTrue(self.project_hub.get_projects())

    @staticmethod
    def get_project_names_and_chances(config_content):
        """Helper method to get project names and chances from project line."""
        names_and_chances = {}
        for project in config_content.split("\n"):
            spec = project.split(":")
            chance = int(spec[1].split(",")[0])
            names_and_chances[spec[0]] = chance
        return names_and_chances

    def test_preference_file(self):
        """Test if chances in preference file are detected."""
        self.init_project_hub(pref_content=self.pref_config_content)
        self.project_hub.fetch_preference_file()
        nc = self.get_project_names_and_chances(self.pref_config_content)
        for name, chance in nc.iteritems():
            self.assertEqual(chance, self.project_hub.preference_for(name))

    def test_best_preferred_chance_is_chosen(self):
        """Test if chances in preference file are detected."""
        self.init_project_hub(pref_content=self.pref_config_content2)
        self.project_hub.fetch_preference_file()
        nc = self.get_project_names_and_chances(self.pref_config_content2)

        best = 0
        for chance in nc.itervalues():
            best = chance if chance > best else best
        for name, chance in nc.iteritems():
            self.assertEqual(best, self.project_hub.preference_for(name))

    def test_invalid_config_file(self):
        """Test that several invalid project lines are detected."""
        self.init_project_hub(config_content=self.invalid_config_content)
        self.assertRaises(SystemExit, self.project_hub.fetch_config_file)

    def test_valid_but_incomplete_config_file(self):
        """Test that valid project lines should always sum up to 100."""
        self.init_project_hub(config_content=self.incomplete_config_content)
        self.assertRaises(SystemExit, self.project_hub.fetch_config_file)

    def test_metadata_option_is_parsed(self):
        self.init_project_hub()
        self.project_hub.parse_shared_and_guest_metadata_file()
        self.assertEqual(self.shared, self.project_hub.shared_meta_file)
        relative_guest = lstrip(self.guest, '/')
        self.assertEqual(relative_guest, self.project_hub.guest_meta_file)


class ProjectManagerTest(BaseDumbqTest):

    """Test suite for the ProjectManager."""

    def test_has_free_space(self):
        self.init_project_manager()

    def test_update_index(self):
        pass

    def test_read_environment_variables(self):
        pass


if __name__ == '__main__':
    unittest.main()
