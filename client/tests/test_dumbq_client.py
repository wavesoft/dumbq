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

        # Mock cernvm environment
        _, self.uuid_fp = tempfile.mkstemp()
        self.config["uuid_file"] = self.uuid_fp
        _, self.cernvmconf_fp = tempfile.mkstemp()
        self.config["local_cernvm_config"] = self.cernvmconf_fp

        # Mock dumbq environment
        self.dumbq_dir = tempfile.mkdtemp()
        self.config["dumbq_dir"] = self.dumbq_dir
        self.www_dir = tempfile.mkdtemp()
        self.config["www_dir"] = self.www_dir

        # Store all the messages to a file
        _, self.test_logfile = tempfile.mkstemp()
        self.config["test_logfile"] = self.test_logfile

        self.setup_config_files()

        # Bind mount directories
        _, self.shared = tempfile.mkstemp()
        _, self.guest = tempfile.mkstemp()
        self.config["shared_meta_file"] = self.shared + "=" + self.guest

        # Set up with a few environment variables
        _, self.envvar_file = tempfile.mkstemp()
        self.config["envvar_file"] = self.envvar_file
        self.envvar_floppy = "GREETING", "hello"
        self.envvar = "FAREWELL", "goodbye"
        write_to_file("/dev/fd0", "=".join(self.envvar_floppy))
        write_to_file(self.envvar_file, "=".join(self.envvar))

        # Tty enabled
        if not os.environ.get("TERM"):
            os.environ["TERM"] = "xterm"
        self.config["base_tty"] = 1

    def setup_config_files(self):
        """Define the configuration files to be tested afterwards."""
        dumbq = "/dumbq/bootstrap/dummy.sh"
        bootstrap = "sft.cern.ch/lcg/external/experimental" + dumbq
        self.valid_config_content = "\n".join((
            "test1:80:sft.cern.ch:" + bootstrap,
            "test2:20:sft.cern.ch:" + bootstrap,
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
        self.dumbq_setup.basic_setup()
        self.dumbq_setup.setup_dumbq_folders()
        self.dumbq_setup.setup_logger(testing=True)
        self.dumbq_setup.setup_public_www()

        config_content = config_content or self.valid_config_content
        pref_content = pref_content or ""
        self.pref_config_source = config["preference_config_source"]
        write_to_file(self.config_source, config_content)
        write_to_file(self.pref_config_source, pref_content)

        self.run_dir = self.config["dumbq_rundir"]

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

    def _formatMessage(self, msg, standardMsg):
        """Honour the longMessage attribute when generating failure messages.
        If longMessage is False this means:
        * Use only an explicit message if it is provided
        * Otherwise use the standard message for the assert

        If longMessage is True:
        * Use the standard message
        * If an explicit message is provided, plus ' : ' and the exp message
        """
        self.longMessage = False
        if not self.longMessage:
            return msg or standardMsg
        if msg is None:
            return standardMsg
        try:
            # don't switch to '{}' formatting in Python 2.X
            # it changes the way unicode input is handled
            return '%s : %s' % (standardMsg, msg)
        except UnicodeDecodeError:
            return '%s : %s' % (safe_repr(standardMsg), safe_repr(msg))

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
        self.dumbq_setup.basic_setup()
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
        """Test that both host and guest are correctly identified."""
        self.init_project_hub()
        self.project_hub.parse_shared_and_guest_metadata_file()
        self.assertEqual(self.shared, self.project_hub.shared_meta_file)
        relative_guest = lstrip(self.guest, '/')
        self.assertEqual(relative_guest, self.project_hub.guest_meta_file)


class BaseProjectManagerTest(BaseDumbqTest):

    """Base class for utilities for both versions of ProjectManager tests."""

    def _simulate_container_creation(self, container_name):
        """As we cannot create a real container, simulate the environment."""
        container_folder = "inst-{0}".format(container_name)
        container_info_fp = os.path.join(self.www_dir, container_folder)
        run_fp = self.run_dir + "/" + container_name

        os.mkdir(container_info_fp)
        write_to_file(run_fp, "")
        return container_info_fp, run_fp


class ProjectManagerTest(BaseProjectManagerTest):

    """Test suite for the ProjectManager.

    Some of the tests in this class are just checking there are not any runtime
    errors when executing them, because we cannot create a project using
    cernvm-fork inside a Docker container. Then, we cannot control the output
    of commands like ``lxc-ls``."""

    def test_update_project_stats(self):
        """Test that the json index file is created."""
        self.init_project_manager()
        index_filepath = os.path.join(self.www_dir, "index.json")
        self.assertFalse(os.path.exists(index_filepath))
        self.project_manager.update_project_stats()
        self.assertTrue(os.path.exists(index_filepath))

    def test_free_space(self):
        """Test there is free space for n (cores) containers at boot."""
        self.init_project_manager()

        try:
            for i in range(multiprocessing.cpu_count()):
                self._simulate_container_creation("test{0}".format(i))
                self.assertTrue(self.project_manager.free_space())
        except OSError:
            failure = "This test fails because `cernvm-fork` is not installed"
            self.fail(failure)

    def test_read_environment_variables(self):
        """Test that environment variables are read from fd0 and file."""
        self.init_project_manager()
        self.assertFalse(self.project_manager.envvars)
        self.project_manager.read_environment_variables()
        envvars = self.project_manager.envvars
        self.assertIn(self.envvar, envvars)
        self.assertIn(self.envvar_floppy, envvars)

    def test_pick_project(self):
        """Test that a random project is chosen."""
        self.init_project_manager()
        picked_project = self.project_manager.pick_project()
        self.assertIn(picked_project, self.project_hub.get_projects())

    def test_stop_project(self):
        """Test that removal of a project is a success.

        Although the project does not exist, the cernvm-fork command exits
        successfully with a 0 errorcode, hence the test passes.
        """
        self.init_project_manager()
        test_container_name = "test"
        folder, flag = self._simulate_container_creation(test_container_name)

        self.assertTrue(os.path.exists(folder))
        self.assertTrue(os.path.exists(flag))

        try:
            result = self.project_manager.stop_project(test_container_name)
        except OSError:
            failure = "This test fails because `cernvm-fork` is not installed"
            self.fail(failure)
        else:
            self.assertTrue(result)
            self.assertFalse(os.path.exists(folder))
            self.assertFalse(os.path.exists(flag))


def with_cernvm_fork():
    return os.environ.get("CERNVM_ENV")


def inside_docker():
    docker_env_file = "/.dockerinit"
    return os.path.exists(docker_env_file)


info_tests = ""
inside_cernvm = with_cernvm_fork() and not inside_docker()

if inside_cernvm:
    class ProjectManagerTestInsideCernVM(BaseProjectManagerTest):

        """Second test suite including more tests for ProjectManager.

        These tests are meant to be run inside a real CernVM environment,
        not Docker. Otherwise, they will fail because ``cernvm-fork`` fails
        while creating a container inside Docker."""

        def test_cleanup_environment(self):
            """Test that resources from inactive containers are removed."""
            self.init_project_manager()
            folder, flag = self._simulate_container_creation("test1")
            folder2, flag2 = self._simulate_container_creation("test2")

            self.assertTrue(os.path.exists(folder))
            self.assertTrue(os.path.exists(folder2))
            self.assertTrue(os.path.exists(flag))
            self.assertTrue(os.path.exists(flag2))

            self.project_manager.cleanup_environment()

            self.assertFalse(os.path.exists(folder))
            self.assertFalse(os.path.exists(folder2))
            self.assertFalse(os.path.exists(flag))
            self.assertFalse(os.path.exists(flag2))

        def test_open_tty(self):
            """Test that a terminal can be opened."""
            self.init_project_manager()
            self.project_manager.run_project()
            any_opened_tty = (self.project_manager.open_tty("test1") or
                              self.project_manager.open_tty("test2"))
            self.assertTrue(any_opened_tty)

        def test_run_project(self):
            """Test that DumbQ is able to run projects."""
            self.init_project_manager()
            started_project = self.project_manager.run_project()
            self.assertTrue(os.path.exists(self.config["www_dir"]))
            self.assertTrue(started_project)
            flag_fp = os.path.join(self.run_dir, started_project)
            self.assertTrue(os.path.exists(flag_fp))

else:
    info_tests = """
*********************************************
** Be careful, some tests haven't been run **
*********************************************

REASON
======
At this moment is not possible to create a LXC container inside Docker.

SOLUTION
========
Run the tests inside a real CernVM environment.
"""


if __name__ == '__main__':
    try:
        unittest.main()
    except SystemExit:
        print(info_tests)
        raise
